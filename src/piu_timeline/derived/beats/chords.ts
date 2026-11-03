import {contracts} from '../contracts.ts';
import {imagePosition} from '../coordinates/measurements.ts';
import {fitTrajectory} from '../coordinates/points.ts';
import {affineDomain}from '../coordinates/phase_clock.ts';
import {equal, linear} from '../math.ts';
import type {Interval, Note, RecordData} from '../types.ts';
const F = contracts.chords;

/** Paired visibility can have a HUD gap while original capture stays continuous. */
function captureMotion(samples:number[][],timeline:RecordData[]):RecordData|null{
 const source=timeline.filter(s=>samples[0][0]<=s.time&&s.time<=samples.at(-1)[0]),at=new Map(source.map(s=>[s.time,s.source_pts]));
 if(source.length<2||samples.some(s=>!Number.isFinite(s[3])||at.get(s[0])!==s[3])||source.some(s=>![s.time,s.source_pts].every(Number.isFinite))||
  source.slice(1).some((s,i)=>s.time<=source[i].time||s.source_pts<=source[i].source_pts||
   Math.max(s.time-source[i].time,s.source_pts-source[i].source_pts)>F.capture_motion.maximum_source_gap_seconds+1e-6))return null;
 const points=samples.map(s=>[s[0],-(s[1]+s[2])/2]),steps=points.slice(1).flatMap(([t,y],i)=>
  t-points[i][0]<=F.capture_motion.maximum_source_gap_seconds+1e-6?[Math.max(0,y-points[i][1])]:[]);
 if(!steps.length)return null;
 const capture=Math.max(...steps),endpoint=Math.max(...samples.map(s=>(s[6]+s[7])/2)),error=capture+endpoint,
  domain=affineDomain(points,error);
 return domain?{format:F.capture_motion,...domain,phase_error_pixels:error,observed_render_step_pixels:capture,
  endpoint_uncertainty_pixels:endpoint,source_pts_range:[source[0].source_pts,source.at(-1).source_pts],source_frames:source.length}:null;
}

export function prepare(data: RecordData, spacing: number): RecordData[] {
  const at = new Map<number, RecordData[]>();
  for (const record of data.head_registration?.notes ?? []) {
    const image = record.coordinate_method === 'native_image_anchors';
    if (!image && (record.coordinate_method !== 'native_cap_measurements' ||
      (record.coordinate_uncertainty_pixels ?? Infinity) > F.coordinate_error_spacing * spacing)) continue;
    const index = record.note, note = data.notes[index], points = new Map<number, number>(fitTrajectory(note).points);
    for (const sample of record.observations) {
      if (image && sample.native_cap_registration_status === 'conflicting') continue;
      const time = sample.time;
      if (!points.has(time)) continue;
      let model = ['native_cap_center', null], endpointError = 0;
      if (image) {
        const position=imagePosition(sample,points.get(time),data.head_registration?.format);
        if(position.kind==='unavailable')throw new Error(`Invalid image chord coordinate: ${position.reason}`);
        if(position.kind==='conflicting_center_projection')continue;
        if(position.kind==='native_cap_center'){
          endpointError=position.uncertaintyPixels;
        }else{
          // A projected center and its raw matching anchor are distinct frames,
          // including when a large uncertainty prevents a certified chord.
          model=[`image_${position.reference.kind==='sha256'?'reference':'template'}`,position.reference.value];
        }
      }
      if (!at.has(time)) at.set(time, []);
      at.get(time).push({index, lane: note.lane, y: points.get(time), pts: sample.source_pts_seconds, model, endpointError,
        reference: image ? (sample.native_cap_reference_template ?? sample.template) : null});
    }
  }
  const pairs = new Map<string, RecordData>();
  for (const [time, points] of [...at].sort((a, b) => a[0] - b[0])) {
    if (Math.max(...points.map(p => p.pts)) - Math.min(...points.map(p => p.pts)) > 1e-6) throw new Error('Native cap measurements disagree on source PTS');
    points.sort((a, b) => a.index - b.index || a.lane - b.lane || a.y - b.y);
    for (let i = 0; i < points.length; i++) for (let j = i + 1; j < points.length; j++) {
      const a = points[i], b = points[j];
      if (a.lane === b.lane || Math.abs(a.pts - b.pts) > 1e-6 || !equal(a.model, b.model)) continue;
      const key = JSON.stringify([a.index, b.index, a.model]);
      if (!pairs.has(key)) pairs.set(key, {a: a.index, b: b.index, model: a.model, samples: []});
      pairs.get(key).samples.push([time, a.y, b.y, a.pts, a.reference, b.reference, a.endpointError, b.endpointError]);
    }
  }
  const result = [];
  for (const {a, b, model, samples} of [...pairs.values()].sort((x, y) => x.a - y.a || x.b - y.b || String(x.model).localeCompare(String(y.model)))) {
    if (samples.length < F.minimum_frames || samples.at(-1)[0] - samples[0][0] < F.minimum_span_seconds || new Set(samples.map(s => s[3])).size !== samples.length) continue;
    const gap = Math.max(...samples.map(s => Math.abs(s[1] - s[2])));
    // Only source-certified per-frame image positions supply endpoint intervals.
    // Every co-observed frame must admit one common physical inter-head gap.
    const measuredBounds = samples.every(s => s[6] > 0 && s[7] > 0);
    const gapRange = measuredBounds ? [Math.max(...samples.map(s => s[2] - s[1] - s[6] - s[7])),
      Math.min(...samples.map(s => s[2] - s[1] + s[6] + s[7]))] : null;
    const maximumGap = F.maximum_gap_spacing * spacing;
    if (gapRange ? Math.max(gapRange[0], -maximumGap) > Math.min(gapRange[1], maximumGap) + 1e-9 : gap > maximumGap) continue;
    const time = samples.map(s => s[0] - samples[0][0]), y = samples.map(s => (s[1] + s[2]) / 2);
    const [velocity, intercept] = linear(time, y), error = Math.max(...y.map((v, i) => Math.abs(v - velocity * time[i] - intercept)));
    const displacement = y[0] - y.at(-1);
    if(displacement<F.minimum_displacement_spacing*spacing)continue;
    const capture=measuredBounds?captureMotion(samples,data.scroll_motion?.samples??[]):null;
    if(!capture&&error>F.maximum_motion_residual_spacing*spacing)continue;
    const endpointError=measuredBounds?Math.max(...samples.map(s=>(s[6]+s[7])/2)):F.coordinate_error_spacing*spacing,
      lower=capture?capture.velocity_range_pixels_per_second[0]:(displacement-2*endpointError)/time.at(-1);
    if (lower <= 0) continue;
    const templates = [...new Set(samples.flatMap(s => s.slice(4, 6)).filter(v => v != null))].sort();
    result.push({lane_spacing_pixels: spacing, peer_notes: [a, b], observed_points: samples.length, maximum_gap_pixels: gap,
      ...(gapRange ? {native_gap_range_pixels: gapRange, endpoint_uncertainty_pixels: samples.map(s => s.slice(6, 8))} : {}),
      ...(['image_reference', 'image_template'].includes(model[0]) ? {measurement_basis: 'shared_image_reference', reference_identity: model[1], reference_templates: templates} : {}),
      ...(model[0] === 'native_cap_center' && templates.length ? {measurement_basis: 'source_bound_native_cap_centers', registered_image_templates: templates} : {}),
      visible_start_seconds: samples[0][0], visible_end_seconds: samples.at(-1)[0], source_pts_seconds: samples.map(s => s[3]),
      minimum_velocity_pixels_per_second: lower, maximum_motion_residual_pixels: error,...(capture?{capture_phase_motion:capture}:{})});
  }
  return result;
}

function maximumGap(proof:RecordData):number{
 const range=proof.native_gap_range_pixels;
 if(range){if(range.length!==2||!range.every(Number.isFinite)||range[0]>range[1])throw Error('Invalid native chord gap interval');
  return Math.max(...range.map(Math.abs));}
 return (F.maximum_gap_spacing+2*F.coordinate_error_spacing)*proof.lane_spacing_pixels;
}

function timeGap(proof:RecordData):Interval{
 const minimum=proof.minimum_velocity_pixels_per_second,gap=proof.native_gap_range_pixels,
  velocity=proof.capture_phase_motion?.velocity_range_pixels_per_second;
 if(!Number.isFinite(minimum)||minimum<=0)throw Error('Invalid native chord velocity bound');
 if(gap)maximumGap(proof);
 if(gap&&velocity){
  if(velocity.length!==2||!velocity.every(Number.isFinite)||velocity[0]<=0||velocity[0]>velocity[1])throw Error('Invalid native chord motion interval');
  const values=gap.flatMap(g=>velocity.map(v=>g/v));return [Math.min(...values),Math.max(...values)];
 }
 if(gap)return [Math.min(0,gap[0]/minimum),Math.max(0,gap[1]/minimum)];
 const limit=maximumGap(proof)/minimum;return [-limit,limit];
}

export function constrain(domains: Interval[], step: number, constraints: RecordData[]): [Interval[], RecordData[]] {
  const edges=constraints.map(p=>{const [lo,hi]=timeGap(p),native=p.native_gap_range_pixels;
    return [p,Math.max(Math.ceil(lo/step-1e-9),native?.[0]>0?1:-Infinity),
      Math.min(Math.floor(hi/step+1e-9),native?.[1]<0?-1:Infinity)] as const;});
  const result = domains.map(d => [...d] as Interval), used = new Set<number>();
  let changed = true;
  while (changed) {
    changed = false;
    edges.forEach(([proof, lo,hi], index) => {
      const [a, b] = proof.indices, first = result[a], second = result[b];
      let narrowed: Interval[];
      if (lo>hi||first[0] > first[1] || second[0] > second[1]) narrowed = [[1, 0], [1, 0]];
      else {
        narrowed = [[Math.max(first[0], second[0] - hi), Math.min(first[1], second[1] - lo)],
          [Math.max(second[0], first[0] + lo), Math.min(second[1], first[1] + hi)]];
        if (narrowed.some(([lo, hi]) => lo > hi)) narrowed = [[1, 0], [1, 0]];
      }
      if (lo===hi || !equal(narrowed, [first, second])) used.add(index);
      if (!equal(narrowed, [first, second])) { [result[a], result[b]] = narrowed; changed = true; }
    });
  }
  return [result, edges.flatMap(([p], i) => used.has(i) ? [p] : [])];
}

export function conflicts(notes: Note[], constraints: RecordData[]): RecordData[] {
  const result = [];
  for (const proof of constraints) {
    const threshold=maximumGap(proof);
    const [a, b] = proof.peer_notes;
    if ([a, b].some(i => notes[i].status !== 'estimated')) continue;
    const delta=notes[b].target_seconds-notes[a].target_seconds,[lo,hi]=timeGap(proof),native=proof.native_gap_range_pixels,
      distance=Math.abs(delta)*proof.minimum_velocity_pixels_per_second;
    if(lo-1e-9<=delta&&delta<=hi+1e-9&&!(native&&(native[0]>0&&delta<=0||native[1]<0&&delta>=0)))continue;
    for (const i of [a, b]) result.push({...proof, note: i, lane: notes[i].lane, check: 'timing_reconstruction',
      reason: 'beat_grid_conflicts_with_native_chord', reconstructed_minimum_gap_pixels: distance, maximum_compatible_gap_pixels: threshold});
  }
  return result;
}
