/** Project measured held intervals into chart objects without a separate head press. */
import type {RecordData} from './types.ts';
const unique = <T>(a: T[]): T[] => [...new Set(a)];
const count = (observations, field) => { const result = {}; for (const o of observations) result[o[field]] = (result[o[field]] ?? 0) + 1; return result; };

export function observedTailRoles(data: RecordData): RecordData[] {
  const records = data.visual_channels?.note_types?.notes ?? [];
  if (data.skin_detector && Object.keys(data.skin_detector).length) return records.flatMap(r => {
    const obs = r.observations, roles = unique<string>(obs.map(o => o.role).filter(r => r !== 'unknown'));
    if (!obs.length || roles.length !== 1 || roles[0] !== 'hold_end') return [];
    const supported = obs.filter(o => o.role === 'hold_end');
    return [{tail_note: r.note, head_note: null, lane: data.notes[r.note].lane, status: 'observed_image_tail_timing_unresolved',
      visible_start_seconds: Math.min(...supported.map(o => o.playback_seconds)), visible_end_seconds: Math.max(...supported.map(o => o.playback_seconds)),
      source_pts_seconds: supported.map(o => o.source_pts_seconds), image_evidence: supported}];
  });
  const types = new Map<number, string[]>(records.map(r => [r.note, unique<string>((r.observations ?? []).map(o => o.kind).filter(k => k !== 'unknown'))]));
  const pairs = new Map(), heads = new Map(), tails = new Map(), own = (map, a, b) => { if (!map.has(a)) map.set(a, new Set()); map.get(a).add(b); };
  for (const r of data.hold_analysis?.unresolved_tracks ?? []) {
    const p = r.cap_continuity ?? {};
    if (p.decision !== 'connected_caps' || p.gap_source_pts_seconds?.length) continue;
    const head = p.head_note, tail = p.tail_note;
    if ([head, tail].some(i => !Number.isInteger(i) || i < 0 || i >= data.notes.length) || head === tail || data.notes[head].lane !== data.notes[tail].lane) continue;
    const connected = new Set(p.connected_source_pts_seconds ?? []), total = new Set([...(p.connected_source_pts_seconds ?? []), ...(p.gap_source_pts_seconds ?? []), ...(p.weak_source_pts_seconds ?? [])]).size;
    if (connected.size < 8 || connected.size < .8 * total || p.visible_end_seconds - p.visible_start_seconds < .12) continue;
    if ([head, tail].some(i => { const t = types.get(i); return !t || t.length !== 1 || t[0] !== 'hold'; })) continue;
    const key = `${head},${tail}`;
    if (!pairs.has(key)) pairs.set(key, []); pairs.get(key).push(p); own(heads, head, tail); own(tails, tail, head);
  }
  const result = [];
  for (const [key, proofs] of pairs) {
    const [head, tail] = key.split(',').map(Number);
    if (heads.get(head).size !== 1 || tails.get(tail).size !== 1 || tails.has(head) || heads.has(tail)) continue;
    result.push({head_note: head, tail_note: tail, lane: data.notes[tail].lane, status: 'observed_connection_timing_unresolved',
      visible_start_seconds: Math.min(...proofs.map(p => p.visible_start_seconds)), visible_end_seconds: Math.max(...proofs.map(p => p.visible_end_seconds)),
      source_pts_seconds: unique<number>(proofs.flatMap(p => p.connected_source_pts_seconds)).sort((a, b) => a - b)});
  }
  return result;
}

export const imageTailRoles = (data: RecordData) => observedTailRoles({...data, skin_detector: {image: true}});

export function projectTypes(data: RecordData, notes: RecordData[], holds: RecordData[]): RecordData[] {
  const records = data.visual_channels?.note_types?.notes;
  if (records == null) return [];
  const by = new Map<number, RecordData>(records.map(r => [r.note, r])), groups = new Map(), byHold = new Map<number, RecordData>(), diagnostics = [];
  for (const h of holds) { groups.set(h.display_note, unique<number>([...h.covered_notes, ...['head_note', 'head_observation_note', 'tail_observation_note'].map(k => h[k]).filter(i => i != null)])); byHold.set(h.display_note, h); }
  const timeline = new Map<number, number>((data.visual_channels?.timeline?.frames ?? []).map(([t, pts]) => [pts, t]));
  notes.forEach((n, i) => {
    if (n.status !== 'estimated') return;
    const members = groups.get(i) ?? [i], hold = byHold.get(i);
    let obs = [...members].sort((a, b) => a - b).flatMap(index => by.get(index)?.observations ?? []);
    if (hold?.start_range) obs = obs.map(o => o.kind === 'tap' && o.playback_seconds >= hold.start_range[0] ? {...o, kind: 'unknown', observed_kind: 'tap', reason: 'hold_processing_remnant'} : o);
    const kinds = new Set(obs.map(o => o.kind).filter(k => k !== 'unknown'));
    if (groups.has(i)) {
      kinds.add('hold');
      const pts = hold.source_pts_range;
      if (pts && pts.every(p => timeline.has(p))) obs.push({kind: 'hold', reason: 'reconstructed_connected_body', source_note: hold.head_note, hold: hold.id,
        playback_seconds: timeline.get(pts[0]), playback_end_seconds: timeline.get(pts[1]), source_pts_seconds: pts[0], source_pts_range: pts});
    }
    const status = kinds.size > 1 ? 'conflict' : kinds.size ? [...kinds][0] : 'unknown';
    Object.assign(n, {type_status: status, type_evidence: obs, type_unknown_reasons: count(obs.filter(o => o.kind === 'unknown'), 'reason')});
    if (['unknown', 'conflict'].includes(status) || status === 'hold' && n.note_type !== 'hold') {
      const proof = obs.filter(o => o.kind !== 'unknown');
      let times = proof.flatMap(o => [o.playback_seconds, o.playback_end_seconds ?? o.playback_seconds]);
      if (!times.length) times = (n.points ?? []).map(p => p[0]); if (!times.length) times = [n.target_seconds];
      diagnostics.push({note: i, lane: n.lane, reason: status === 'conflict' ? 'note_type_conflict' : 'note_type_unresolved', visible_start_seconds: Math.min(...times), visible_end_seconds: Math.max(...times),
        observed_points: obs.length, type_evidence: proof, type_unknown_reasons: n.type_unknown_reasons, hold: n.hold_id ?? null});
    }
  });
  return diagnostics;
}

export function chartProjection(data: RecordData): RecordData {
  const holds = data.hold_analysis?.holds ?? [], notes = (data.notes ?? []).map(n => ({...n}));
  if (!data.hold_analysis || !Object.keys(data.hold_analysis).length) return {...data, notes, note_type_diagnostics: projectTypes(data, notes, [])};
  const suppressed = new Set<number>(holds.flatMap(h => [...h.covered_notes, h.head_note, h.tail_note]).filter(i => i != null));
  const tailRoles = observedTailRoles(data).filter(r => !suppressed.has(r.tail_note)); tailRoles.forEach(r => suppressed.add(r.tail_note));
  for (const i of suppressed) Object.assign(notes[i], {status: 'excluded', reason: 'long_note_body_or_tail', note_type: 'hold_component'});
  for (const r of tailRoles) Object.assign(notes[r.tail_note], {reason: 'observed_hold_tail_pending_geometry', hold_cap_role: 'tail', observed_hold_head: r.head_note});
  const projected = [], unresolved = [];
  for (const original of holds) {
    const h = {...original, covered_notes: unique<number>([...original.covered_notes, original.head_note, original.tail_note].filter(i => i != null)).sort((a, b) => a - b), input_requirement: 'held_state', requires_head_press: false};
    const start = h.start_range, target = h.start_censored ? start[1] : (start[0] + start[1]) / 2;
    let head = h.head_note;
    if (head == null || !suppressed.has(head)) {
      head = notes.length; notes.push({lane: h.lane, points: [], target_seconds: target});
      const observed = h.head_observation_note;
      if (observed != null) {
        notes[head].source_head_observation = observed;
        for (const field of ['timing_reconstruction', 'beat_reconstruction']) if (Object.hasOwn(data.notes[observed], field)) notes[head][field] = {...data.notes[observed][field]};
      }
    }
    Object.assign(notes[head], {status: 'estimated', reason: null, note_type: 'hold', hold_id: h.id, input_requirement: 'held_state', requires_head_press: false, target_seconds: target,
      prediction_uncertainty_seconds: h.start_censored ? 0 : (start[1] - start[0]) / 2});
    if (notes[head].timing_reconstruction?.status === 'failed' || notes[head].beat_reconstruction?.status === 'failed') Object.assign(notes[head], {status: 'excluded', reason: 'timing_reconstruction_failed'});
    h.display_note = head;
    if (notes[head].status === 'estimated') projected.push(h); else unresolved.push({...h, projection_failure: notes[head].reason});
  }
  return {...data, notes, note_type_diagnostics: projectTypes(data, notes, projected), hold_analysis: {...data.hold_analysis, holds: projected, unresolved_holds: unresolved, observed_tail_roles: tailRoles}};
}
