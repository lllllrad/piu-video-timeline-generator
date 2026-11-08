import {approachPoints} from './coordinates/approach.ts';
import {linear, mean, median, rms, std, sum} from './math.ts';
import {refine} from './registration.ts';
import {contracts} from './contracts.ts';
import type {RecordData} from './types.ts';

export function registered(tracks: RecordData[], timeline: RecordData[], height: number, spacing: number, receptor: number, bottom: number): RecordData {
  const at = new Map<number, RecordData>();
  tracks.forEach((track, i) => { for (const [t, y] of approachPoints(track,receptor,spacing,bottom)) {
    if (!at.has(t)) at.set(t, {}); at.get(t)[i] = [track.lane, y];
  } });
  const samples = [],nativeConflicts=[];
  let previous = null, anchor = null, chunk = -1;
  for (const native of timeline) {
    const time = native.time, current = at.get(time) ?? {};
    let displacement = null, observed = null, support = 0, lanes = 0, scatter = 0, basis = 'unsupported',nativeInterval=null;
    if (previous && 0 < time - previous.time && time - previous.time <= .05 + 1e-6) {
      const before = at.get(previous.time) ?? {};
      const pairs = Object.keys(before).filter(i => Object.hasOwn(current, i)).map(i => [before[i][1] - current[i][1], current[i][0], Number(i)]);
      if (pairs.length) {
        const center = median(pairs.map(p => p[0])); observed = center;
        const kept = pairs.filter(p => Math.abs(p[0] - center) <= 1.5);
        support = kept.length; lanes = new Set(kept.map(p => p[1])).size;
        const qualified=pairs.filter(p=>tracks[p[2]].coordinate_basis==='native_cap_center'&&
          Number.isFinite(tracks[p[2]].registration_uncertainty_pixels)&&tracks[p[2]].registration_uncertainty_pixels>0);
        if(qualified.length){
          const intervals=qualified.map(p=>[p[0]-2*tracks[p[2]].registration_uncertainty_pixels,p[0]+2*tracks[p[2]].registration_uncertainty_pixels]);
          const distinctLanes=new Set(qualified.map(p=>p[1])).size,
            cadenceLimit=spacing*30*(time-previous.time),
            captureLimit=distinctLanes>=2?spacing*30*contracts.frame_tracking.maximum_capture_interval_seconds:cadenceLimit;
          const lo=Math.max(0,...intervals.map(r=>r[0])),hi=Math.min(captureLimit,...intervals.map(r=>r[1]));
          if(lo<=hi+1e-8){
            displacement=Math.max(lo,Math.min(hi,median(qualified.map(p=>p[0]))));support=qualified.length;
            lanes=new Set(qualified.map(p=>p[1])).size;
            scatter=Math.max(.35,std(qualified.map(p=>p[0])),displacement-lo,hi-displacement);
            basis=support>1?'independent_registered_peers':'measured_cap_displacement';
            anchor=[time,new Set(qualified.map(p=>p[2]))];
            nativeInterval={range_pixels:[lo,hi],notes:qualified.map(p=>p[2]),endpoint_intervals_pixels:intervals};
            if(lo>cadenceLimit+1e-8)for(const p of qualified)nativeConflicts.push({note:p[2],lane:p[1],
              reason:'native_motion_cadence_unresolved',check:'timing_reconstruction',observed_points:qualified.length,
              visible_start_seconds:previous.time,visible_end_seconds:time,source_pts_seconds:[previous.source_pts,native.source_pts],
              displacement_range_pixels:[lo,hi],source_cadence_limit_pixels:cadenceLimit,
              interpretation:'measured_displacement_without_engine_time_assumption'});
          }else{
            for(const p of qualified)nativeConflicts.push({note:p[2],lane:p[1],reason:'native_frame_displacement_conflict',check:'timing_reconstruction',
              visible_start_seconds:previous.time,visible_end_seconds:time,observed_points:2,
              source_pts_seconds:[previous.source_pts,native.source_pts],peer_notes:qualified.map(p=>p[2]),
              displacement_intervals_pixels:intervals,forward_intersection_pixels:[lo,hi],
              failure_detail:Math.max(...intervals.map(r=>r[0]))>Math.min(...intervals.map(r=>r[1]))?
                'inconsistent_native_displacements':hi<0?'reverse_motion':'excessive_frame_displacement'});
          }
        }else if (support >= 2 && (lanes >= 2 || Math.max(...kept.map(p => current[p[2]][1])) - Math.min(...kept.map(p => current[p[2]][1])) > .65 * spacing) && -.75 <= center && center <= spacing * 30 * (time - previous.time)) {
          displacement = Math.max(0, median(kept.map(p => p[0]))); scatter = Math.max(.35, std(kept.map(p => p[0])));
          basis = 'independent_registered_peers'; anchor = [time, new Set(kept.map(p => p[2]))];
        } else if (pairs.length === 1) {
          const track=tracks[pairs[0][2]],error=track.registration_uncertainty_pixels;
          const measured=track.coordinate_basis==='native_cap_center'&&Number.isFinite(error)&&error>0;
          const continued=anchor&&time-anchor[0]<=.25+1e-6&&anchor[1].has(pairs[0][2]);
          if((measured||continued)&&-Math.max(.75,measured?2*error:0)<=pairs[0][0]&&pairs[0][0]<=spacing*30*(time-previous.time)){
            displacement=Math.max(0,pairs[0][0]);support=lanes=1;scatter=Math.max(.75,measured?error:0);
            basis=measured?'measured_cap_displacement':'registered_identity_continuation';
          }
        }
      }
    }
    let phase = 0, variance = 0;
    if (displacement === null) { chunk++; anchor = null; }
    else { phase = samples.at(-1).phase + displacement; variance = samples.at(-1).variance + scatter ** 2; }
    samples.push({...native, phase, pairwise_phase_pixels: phase, observed_peer_displacement_pixels: observed, variance, chunk,
      support: displacement !== null ? support : 0, lanes: displacement !== null ? lanes : 0, displacement_basis: basis,
      ...(nativeInterval?{native_displacement_interval:nativeInterval}:{})});
    previous = native;
  }
  const result=refine(samples,tracks,receptor,spacing,bottom);
  return {...result,coordinate_conflicts:[...result.coordinate_conflicts,...nativeConflicts],registered_positions:Object.fromEntries(at)};
}

export function fitTrack(track: RecordData, receptor: number, spacing: number): RecordData {
  const result: RecordData = {lane: track.lane, points: track.points, status: 'excluded', reason: null, target_seconds: null};
  const visible = track.points.filter(p => p[1] > receptor + .85 * spacing);
  if (visible.length < 4 || visible.at(-1)[0] - visible[0][0] < .065) return {...result, reason: 'insufficient_track'};
  const points = visible.slice(-12), t = points.map(p => p[0] - points.at(-1)[0]), y = points.map(p => p[1]);
  const [velocity, intercept] = linear(t, y), residual = rms(y.map((v, i) => v - velocity * t[i] - intercept));
  Object.assign(result, {velocity_pixels_per_second: velocity, residual_pixels: residual});
  if (velocity >= -spacing) return {...result, reason: 'stopped_or_reverse_scroll'};
  const half = Math.floor(points.length / 2), first = linear(t.slice(0, half), y.slice(0, half)), last = linear(t.slice(half), y.slice(half));
  const change = Math.abs(first[0] - last[0]) / Math.max(Math.abs(velocity), 1);
  result.speed_change_fraction = change;
  const quantization = 2 / Math.max(Math.abs(velocity) * (t.at(-1) - t[half]), 1);
  const variance = (ts, ys, fit) => {
    const errors = ys.map((v, i) => v - fit[0] * ts[i] - fit[1]);
    return sum(errors.map(v => v * v)) / Math.max(1, ts.length - 2) / Math.max(sum(ts.map(v => (v - mean(ts)) ** 2)), 1e-9);
  };
  const slopeError = 3 * Math.sqrt(variance(t.slice(0, half), y.slice(0, half), first) + variance(t.slice(half), y.slice(half), last)) / Math.abs(velocity);
  if (residual > spacing * .14 || change > .18 + quantization + slopeError) {
    const gaps = points.slice(1).flatMap((p, i) => p[0] - points[i][0] > .06 ? [i] : []);
    if (gaps.length) {
      const latest = points.slice(gaps.at(-1) + 1);
      if (latest.length >= 4 && latest.at(-1)[0] - latest[0][0] >= .065) {
        const recovered = fitTrack({...track, points: latest}, receptor, spacing);
        if (recovered.status === 'estimated') return {...recovered, points: result.points, fit_method: 'linear_after_occlusion'};
      }
    }
    return {...result, reason: 'variable_speed_or_tracking_error'};
  }
  const target = points.at(-1)[0] + (receptor - intercept) / velocity, extrapolation = target - points.at(-1)[0];
  if (!(0 <= extrapolation && extrapolation <= .25) || intercept - receptor > 2.5 * spacing) return {...result, reason: 'receptor_not_observed_closely'};
  const step = median(points.slice(1).map((p, i) => p[0] - points[i][0]));
  let heldSince = points[0][0], holdSpan = 0;
  points.slice(1).forEach((p, i) => { if (Math.abs(p[1] - points[i][1]) > .75) heldSince = p[0]; holdSpan = Math.max(holdSpan, p[0] - heldSince); });
  return {...result, status: 'estimated', target_seconds: target, prediction_uncertainty_seconds: Math.max(residual / Math.abs(velocity), (track.registration_uncertainty_pixels ?? 0) / Math.abs(velocity), (step + holdSpan) / 2)};
}
