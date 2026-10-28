/** Independent chart events sampled into the saved native-observation contract. */
import type {RecordData} from '../../src/piu_timeline/derived/types.ts';
import {parse} from '../../src/piu_timeline/derived/charts/ucs.ts';

export function template(split = 48, rows = 384) {
  return parse(`:Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=${split}\n` + '.....\n'.repeat(rows));
}

export interface NativeCapture {
  end?: number;
  repeated?: [number, number][];
  dropped?: number[];
  renderTime?: (recordingTime: number) => number;
}
export function nativeScene(events: [number, number][], spacing = 40, fps = 60, lanes = 5, capture: NativeCapture = {}): RecordData {
  const width = spacing * 16.25, height = spacing * 9.125, receptor = spacing * 1.3, velocity = spacing * 6;
  const times = Array.from({length: Math.round(((capture.end ?? 1.05) - .2) * fps) + 1}, (_, i) => .2 + i / fps).filter((_, i) => !capture.dropped?.includes(i));
  const rendered = (time: number) => {
    const interval = capture.repeated?.find(([lo, hi]) => lo - 1e-9 <= time && time <= hi + 1e-9);
    if (!interval) return capture.renderTime?.(time) ?? time;
    const before = times.filter(t => t < interval[0] - 1e-9).at(-1);
    if (before === undefined) throw Error('Repeated frame requires an earlier captured image');
    return capture.renderTime?.(before) ?? before;
  };
  const notes = [], registrations = [], offsets = [];
  events.forEach(([target, lane], index) => {
    const points = times.map(t => [t, receptor + velocity * (target - rendered(t))])
      .filter(([, y]) => receptor + .85 * spacing < y && y < .95 * height - .55 * spacing);
    notes.push({lane, status: 'estimated', target_seconds: target, prediction_uncertainty_seconds: .5 / fps, points,
      velocity_pixels_per_second: -velocity, motion_clock: {origin: 0, velocity, intercept: 0}, motion_target_phase: velocity * target});
    registrations.push({note: index, status: 'registered', coordinate_method: 'native_cap_measurements', coordinate_uncertainty_pixels: .025 * spacing,
      observations: points.map(([time]) => ({time, source_pts_seconds: 80 + time}))});
    offsets.push({note: index, offset_pixels: receptor + velocity * target});
  });
  return {analysis_width: width, analysis_height: height, start_seconds: .2, end_seconds: 2.2,
    layout: {receptor_y: receptor / height, note_y_max: .95, lanes: Array.from({length: lanes}, (_, i) => ({x: .1 + i * spacing / width}))},
    notes, head_registration: {notes: registrations},
    scroll_motion: {samples: times.map(time => ({time, source_pts: 80 + time, phase: velocity * rendered(time), variance: 0, support: lanes, chunk: 0})),
      coordinate_registration: {chunks: [{chunk: 0, status: 'fitted', head_offsets: offsets}]}}};
}

/** A broad crossing initially fits a coarse row, then loses native support. */
export function neighborReferenceScene(spacing=40,fps=60) {
  const events:[number,number][]=Array.from({length:5},(_,i)=>[1.125+i/8,i%5]);
  events.push([1.875+1/128,0]);
  for(let i=0;i<7;i++)events.push([2+i/8,(i+1)%5]);
  const data=nativeScene(events,spacing,fps,5,{end:3}),velocity=spacing*6;
  data.notes.forEach((n,i)=>{
    const bias=i<5?(i%2===0?1:-1)*.02375*spacing:0;
    n.points=n.points.map(([t,y])=>[t,y+bias]);
    data.scroll_motion.coordinate_registration.chunks[0].head_offsets[i].offset_pixels+=bias;
    n.motion_target_phase+=bias;n.target_seconds=events[i][0]+bias/velocity;
    n.prediction_uncertainty_seconds=.005;n.fit_method='shared_scroll_clock';
  });
  Object.assign(data.notes[5],{target_seconds:1.879,motion_clock:null,fit_method:'shared_scroll_frame_bounds',
    native_clock_warning:{reason:'shared_subframe_clock_unresolved'}});
  data.timing_reconstruction={status:'failed',failed_notes:1,restored_notes:data.notes.length,
    warnings:[{note:5,lane:data.notes[5].lane,reason:'shared_subframe_clock_unresolved',check:'timing_reconstruction',
      visible_start_seconds:1.874,visible_end_seconds:1.884}]};
  const heads=data.scroll_motion.coordinate_registration.chunks[0].head_offsets.map((h,i)=>({
    offset:h.offset_pixels,lane:data.notes[i].lane,native_note:i,native_points:data.notes[i].points.length,
    native_maximum_error_pixels:0,source_pts_range:[80+data.notes[i].points[0][0],80+data.notes[i].points.at(-1)[0]]}));
  const groups=[events.flatMap(([t],i)=>t<2?[i]:[]),events.flatMap(([t],i)=>t>=2?[i]:[])].map(indices=>({
    notes:indices,targets:indices.map(i=>data.notes[i].target_seconds),errors:indices.map(i=>data.notes[i].prediction_uncertainty_seconds),bpm:120,origin:0,
    native_coordinates:[{chunk:0,lane_spacing_pixels:spacing,
      heads:Object.fromEntries(indices.map((i,j)=>[j,heads[i]])),
      neighbor_heads:Object.fromEntries(heads.flatMap((h,i)=>indices.includes(i)?[]:[[i,h]]))}]}));
  return {data,events,groups};
}

/** Captured endpoints with independent registration errors; truth stays rigid. */
export function holdEndpointScene(length: number, scale = 1, delays: number[] = []) {
  const times = Array.from({length: 12}, (_, i) => .2 + i / 60 + (delays[i] ?? 0));
  const headError = [-.75, .5, -.25, .75], tailError = [.75, -.5, .25, -.75];
  return times.map((time, i) => ({time, source_pts_seconds: 80 + time,
    head_y: scale * (200 - 180 * time + headError[i % 4]),
    tail_y: scale * (200 - 180 * time + length + tailError[i % 4]), head_uncertainty: scale, tail_uncertainty: scale}));
}

/** Registered reference heads with independently bounded, fixed anchor errors. */
export function coordinateReferenceScene(spacing = 40, biases = [1,-1,-1,-1,-1,-1,-1]) {
  const events: [number,number][] = Array.from({length:7},(_,i)=>[.5+i/8,i%5]);
  const data = nativeScene(events,spacing,60,5,{end:1.5}), error = .025*spacing;
  for (const [i,bias] of biases.entries()) {
    data.notes[i].points = data.notes[i].points.map(([t,y])=>[t,y+bias*error]);
    data.scroll_motion.coordinate_registration.chunks[0].head_offsets[i].offset_pixels += bias*error;
  }
  const references = data.notes.map((n,i)=>({note:i,lane:n.lane,target_seconds:events[i][0],
    offset:data.scroll_motion.coordinate_registration.chunks[0].head_offsets[i].offset_pixels}));
  return {data,references,velocity:spacing*6,intercept:spacing*1.3+spacing*6*.5,error};
}

/** Image-role observations of a rigid hold, independent of endpoint clocks. */
export function imageHoldScene(scale=1,fps=50){
 const layout={receptor_y:.05,lanes:Array.from({length:5},(_,i)=>({x:.1+i*.1,color:'blue'}))};
 const data:RecordData={analysis_width:200*scale,analysis_height:300*scale,start_seconds:0,end_seconds:2,
  game_roi:[0,0,200*scale,300*scale],layout,skin_detector:{contract:{schema:1}},notes:[]};
 const native:RecordData[]=Array.from({length:Math.round(.18*fps)+1},(_,i)=>{
  const time=i/fps,y=100-100*time;
  const shapes=[['hold_start',y,[10,y-10,30,y+25]],['hold_end',y+60,[10,y+35,30,y+70]],['hold_body',y+35,[16,y+20,24,y+50]]];
  return {playback_seconds:time,source_pts_seconds:80+time,skin_observations:shapes.map(([role,anchor,box])=>({
   lane:0,x:.1,y:Number(anchor)/300,role,template:role,skin:'synthetic',region_errors:{cap:0,connection:0},
   bounds_pixels:(box as number[]).map(v=>v*scale)}))};
 });
 for(const [offset,target]of [[0,.85],[60,1.45]])data.notes.push({lane:0,status:'estimated',target_seconds:target,
  prediction_uncertainty_seconds:.01,velocity_pixels_per_second:-100*scale,
  points:native.map(f=>[f.playback_seconds,(100-100*f.playback_seconds+offset)*scale])});
 const rows={hold_start:[[0,35]],hold_end:[[0,35]],hold_body:[[0,30]]};
 const caps={hold_start:[[0,20]],hold_end:[[15,35]],hold_body:[]};
 const scaled=r=>Object.fromEntries(Object.entries(r).map(([role,runs])=>[role,(runs as number[][]).map(run=>run.map(v=>v*scale))]));
 return {data,native,references:scaled(rows),cap_references:scaled(caps)};
}

/** Two adjacent source holds whose compared image margins touch across the gap. */
export function adjacentImageHolds(scale=1,fps=50){
 const s=imageHoldScene(scale,fps),offsets=[0,40,60,100];
 s.data.notes=offsets.map((offset,i)=>({lane:0,status:'estimated',target_seconds:.85+offset/100,
  prediction_uncertainty_seconds:.01,velocity_pixels_per_second:-100*scale,
  points:s.native.map(f=>[f.playback_seconds,(100-100*f.playback_seconds+offset)*scale])}));
 for(const f of s.native){
  const y=100-100*f.playback_seconds;
  f.skin_observations=offsets.map((offset,i)=>({lane:0,x:.1,y:(y+offset)/300,role:i%2?'hold_end':'hold_start',
   template:i%2?'hold_end':'hold_start',skin:'synthetic',region_errors:{cap:0,connection:0},
   bounds_pixels:[10,y+offset-(i%2?25:10),30,y+offset+(i%2?10:25)].map(v=>v*scale)}));
  for(const offset of[0,60])f.skin_observations.push({lane:0,x:.1,y:(y+offset+35)/300,role:'hold_body',template:'hold_body',
   skin:'synthetic',region_errors:{cap:0,connection:0},bounds_pixels:[16,y+offset+20,24,y+offset+50].map(v=>v*scale)});
 }
 return s;
}
