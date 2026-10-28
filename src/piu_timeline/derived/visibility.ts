/** Audit measured source trajectories independently of chart and input acceptance. */
import {equal, linear, lowerBound, mean, median, rms, sum, upperBound} from './math.ts';
import {classify} from './scroll.ts';
import {contracts} from './contracts.ts';
import type {RecordData} from './types.ts';
export const FORMAT = contracts.visibility;
const EPS = 1e-6;

function occluders(data, lane, y, spacing, regions): string[] {
  const x = data.layout.lanes[lane].x * data.analysis_width, half = .5 * spacing, width = data.analysis_width, height = data.analysis_height;
  return regions.filter(({rect: [rx, ry, rw, rh]}) => x - half < (rx + rw) * width && rx * width < x + half && y - half < (ry + rh) * height && ry * height < y + half).map(r => r.id);
}
function laneSpacing(data): number { const xs = data.layout.lanes.map(l => l.x * data.analysis_width); return median(xs.slice(1).map((x, i) => x - xs[i])); }

export function motionWarnings(data: RecordData, frames: RecordData[], regions: RecordData[]): RecordData[] {
  const result = [], layout = data.layout ?? {};
  if ((layout.lanes ?? []).length < 2) return result;
  const height = data.analysis_height, spacing = laneSpacing(data), pts = new Map(frames.map(f => [f.playback_seconds, f.source_pts_seconds]));
  (data.notes ?? []).forEach((note, ni) => {
    const points = (note.points ?? []).filter(([t, y]) => layout.receptor_y * height + .85 * spacing < y && y < (layout.note_y_max ?? .95) * height - .55 * spacing && !occluders(data, note.lane, y, spacing, regions).length);
    if (points.length < 4) return;
    const record = (reason, lo, hi, measurements) => ({note: ni, lane: note.lane, reason, check: 'scroll_motion', visible_start_seconds: lo, visible_end_seconds: hi, observed_points: points.length,
      source_pts_seconds: [pts.get(lo) ?? null, pts.get(hi) ?? null], ...measurements});
    let start = 0;
    const stops = [];
    for (let j = 1; j < points.length; j++) if (points[j][0] - points[j - 1][0] > .05 + EPS || Math.abs(points[j][1] - points[start][1]) > .75) {
      if (j - start >= 4 && points[j - 1][0] - points[start][0] >= .1 - EPS) stops.push([points[start][0], points[j - 1][0]]);
      start = j;
    }
    if (points.length - start >= 4 && points.at(-1)[0] - points[start][0] >= .1 - EPS) stops.push([points[start][0], points.at(-1)[0]]);
    for (const [lo, hi] of stops) result.push(record('possible_scroll_stop_or_capture_freeze', lo, hi, {stationary_duration_seconds: hi - lo, position_tolerance_pixels: .75}));
    const windows = [];
    for (let i = 0; i < points.length - 3; i += 4) {
      const block = points.slice(i, i + 4), span = block.at(-1)[0] - block[0][0];
      if (span < .05 - EPS || block.slice(1).some((p, j) => p[0] - block[j][0] > .05 + EPS)) continue;
      const x = block.map(p => p[0] - block[0][0]), y = block.map(p => p[1]), [slope, intercept] = linear(x, y);
      const residual = y.map((v, j) => v - (slope * x[j] + intercept)), center = mean(x);
      const error = 3 * Math.sqrt(sum(residual.map(v => v * v)) / Math.max(1, x.length - 2) / Math.max(sum(x.map(v => (v - center) ** 2)), 1e-9)) + 2 / span;
      windows.push([block[0][0], block.at(-1)[0], slope, error]);
    }
    const reverse = [];
    for (const w of windows) {
      if (w[2] <= w[3]) continue;
      if (!reverse.length || w[0] - reverse.at(-1).at(-1)[1] > .05 + EPS) reverse.push([]);
      reverse.at(-1).push(w);
    }
    for (const run of reverse) result.push(record('reverse_scroll_motion', run[0][0], run.at(-1)[1], {direction: 'downward', observed_points: 4 * run.length, direction_windows: run.length,
      velocity_lower_bound_pixels_per_second: Math.min(...run.map(w => w[2] - w[3])), velocity_upper_bound_pixels_per_second: Math.max(...run.map(w => w[2] + w[3]))}));
    windows.slice(1).forEach((after, i) => {
      const before = windows[i];
      if (after[0] - before[1] > .05 + EPS || Math.abs(after[2] - before[2]) <= before[3] + after[3]) return;
      result.push(record('scroll_speed_change', before[0], after[1], {velocity_before_pixels_per_second: before[2], velocity_after_pixels_per_second: after[2], velocity_error_before: before[3], velocity_error_after: after[3]}));
    });
  });
  return result;
}

export function continuity(data: RecordData, frames: RecordData[], regions: RecordData[]): RecordData {
  const warnings = [], occlusions = [], exits = [];
  if (!frames.length || !data.layout?.lanes?.length) return {format: FORMAT, warnings: [], known_occlusions: [], accounted_exits: [], counts: {}};
  const times = frames.map(f => f.playback_seconds), height = data.analysis_height, layout = data.layout, spacing = laneSpacing(data), receptor = layout.receptor_y * height;
  const peers = new Map<number, RecordData>((data.scroll_motion?.samples ?? []).map(s => [s.time, s]));
  const processing = new Map<number, RecordData>((data.visual_channels?.processing?.notes ?? []).map(p => [p.note, p]));
  (data.notes ?? []).forEach((note, ni) => {
    const points = note.detected_points ?? note.points ?? [];
    if (!points.length) return;
    const observed = new Set(points.map(p => p[0])), pending = [];
    points.forEach(([t, y], pi) => {
      const last = pi === points.length - 1, end = last ? Math.min(times.at(-1), t + .65) : points[pi + 1][0];
      const firstFrame = upperBound(times, t), lastFrame = last ? upperBound(times, end) : lowerBound(times, end);
      if (firstFrame >= lastFrame) return;
      const recent = points.slice(Math.max(0, pi - 11), pi + 1);
      let velocity = null;
      if (recent.length >= 4 && recent.at(-1)[0] - recent[0][0] >= .065) {
        const x = recent.map(p => p[0] - t), ys = recent.map(p => p[1]), [slope, intercept] = linear(x, ys), residual = rms(ys.map((v, i) => v - (slope * x[i] + intercept)));
        if (slope < -spacing && residual <= .14 * spacing) velocity = slope;
      }
      const startPeer = peers.get(t);
      for (let fi = firstFrame; fi < lastFrame; fi++) {
        const frame = frames[fi], now = times[fi];
        if (observed.has(now)) continue;
        const peer = peers.get(now);
        let predicted, method;
        if (startPeer && peer && startPeer.chunk === peer.chunk && startPeer.coordinate_status !== 'failed' && peer.coordinate_status !== 'failed') { predicted = y - (peer.phase - startPeer.phase); method = 'peer_displacement'; }
        else if (!last) { const [nt, ny] = points[pi + 1]; predicted = y + (ny - y) * (now - t) / (nt - t); method = 'bounded_reappearance_interpolation'; }
        else if (velocity !== null) { predicted = y + velocity * (now - t); method = 'local_approach_extrapolation'; }
        else { predicted = y; method = 'last_observed_position_only'; }
        const base = {note: ni, lane: note.lane, visible_start_seconds: now, visible_end_seconds: now, source_pts_seconds: [frame.source_pts_seconds, frame.source_pts_seconds],
          last_observed_seconds: t, last_observed_y: y, expected_y: predicted, position_method: method, observed_points: points.length};
        if (predicted <= receptor + .85 * spacing) { if (last) exits.push({...base, reason: 'head_enters_receptor_detection_boundary'}); break; }
        const same = (frame.notes ?? []).filter(n => n.lane === note.lane && Math.abs(n.y * height - predicted) <= 2);
        if (same.length === 1) { if (last) { exits.push({...base, reason: 'native_detection_continues_under_another_track'}); break; } continue; }
        const hud = occluders(data, note.lane, predicted, spacing, regions), loss = processing.get(ni) ?? {};
        if (hud.length) pending.push(['known_occlusions', {...base, reason: 'documented_hud_occlusion', regions: hud}]);
        else if (last && loss.status === 'visibility_modified' && loss.visibility_loss?.range && now >= loss.visibility_loss.range[0]) pending.push(['known_occlusions', {...base, reason: 'chart_visibility_modifier', gimmick_candidates: loss.gimmick_candidates}]);
        else pending.push(['warnings', {...base, reason: last ? 'unexplained_head_disappearance' : 'unexplained_head_detection_gap', check: 'note_visibility'}]);
        if (last && method === 'last_observed_position_only') break;
      }
    });
    const groups = [];
    for (const [destination, record] of pending) {
      const signature = [destination, record.reason, record.regions ?? [], record.last_observed_seconds], previous = groups.at(-1);
      if (previous && equal(previous.signature, signature) && record.visible_start_seconds - previous.record.visible_end_seconds <= .05) {
        Object.assign(previous.record, {visible_end_seconds: record.visible_end_seconds, missing_frames: previous.record.missing_frames + 1}); previous.record.source_pts_seconds[1] = record.source_pts_seconds[1];
      } else groups.push({signature, destination, record: {...record, missing_frames: 1}});
    }
    for (const g of groups) (g.destination === 'warnings' ? warnings : occlusions).push(g.record);
  });
  const native = motionWarnings(data, frames, regions), [remaining, pauses] = classify(data, native, 'pause'), [unexplained, speeds] = classify(data, remaining, 'speed');
  warnings.push(...unexplained);
  const counts = {}; for (const w of warnings) counts[w.reason] = (counts[w.reason] ?? 0) + 1;
  return {format: FORMAT, native_motion_warnings: native, known_motion_effects: [...pauses, ...speeds], warnings, known_occlusions: occlusions, accounted_exits: exits, regions, counts};
}
