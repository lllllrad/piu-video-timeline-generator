/** Endpoint timing consumes measured image topology; it never creates image proof. */
import {inputNotes} from './input.ts';
import {Store,implementation} from '../pipeline/store.ts';
import type {RecordData} from '../types.ts';

function range(note:RecordData):number[]|null{
 if(note.status!=='estimated'||note.timing_reconstruction?.status==='failed'||!Number.isFinite(note.target_seconds))return null;
 const r=note.geometry_native_range??[note.target_seconds-note.prediction_uncertainty_seconds,note.target_seconds+note.prediction_uncertainty_seconds];
 return r.length===2&&r.every(Number.isFinite)&&r[0]<=r[1]?[...r]:null;
}
export function project(source:RecordData[],geometry:RecordData):RecordData{
 const notes=inputNotes(source),holds=[],warnings=(geometry.unresolved_tracks??[]).map(w=>({...w})),owners=new Map();
 for(const c of geometry.image_connections){
  const head=c.head_note,tail=c.tail_note,first=notes[head],last=notes[tail];
  if(!first||!last||head===tail||first.lane!==last.lane||first.lane!==c.lane)throw Error('Invalid image connection endpoints');
  const start=range(first),end=range(last);
  if(!start||!end||last.target_seconds<=first.target_seconds){
   const times=[...first.points,...last.points].map(p=>p[0]);
   if(!times.length||!times.every(Number.isFinite))throw Error('Image connection has no native observation timeline');
   warnings.push({note:head,tail_note:tail,lane:c.lane,reason:'hold_endpoint_timing_unresolved',
    failure_detail:'connected_image_endpoints_without_ordered_timing',image_connection_id:c.id,geometry_status:'connected',
    visible_start_seconds:Math.min(...times),visible_end_seconds:Math.max(...times),source_pts_range:c.source_pts_range,
    observed_points:c.body_frames,endpoint_failures:[head,tail].map(i=>({note:i,status:notes[i].status,
     reason:notes[i].reason??null,timing_status:notes[i].timing_reconstruction?.status??null}))});
   continue;
  }
  const h:RecordData={...c,id:holds.length,image_connection_id:c.id,start_range:start,end_range:end,start_censored:false,end_censored:false};
  const native=[head,tail].filter(i=>Object.hasOwn(notes[i],'geometry_native_range'));
  if(native.length)Object.assign(h,{geometry_native_endpoint_notes:native,chart_timing_status:'unresolved',
   geometry_source_failures:native.map(i=>({note:i,...notes[i].geometry_source_failure}))});
  owners.set(c.id,h.id);holds.push(h);
 }
 for(const w of warnings)if(w.image_connection_id!=null)w.hold=owners.get(w.image_connection_id)??null;
 return {...geometry,holds,unresolved_tracks:warnings};
}
export function projectCached(input:RecordData,directory:string):RecordData{
 if(input.schema!==1||!Array.isArray(input.notes)||!Array.isArray(input.geometry?.image_connections))throw Error('Invalid image timing input');
 return new Store(directory).run('hold-intervals',implementation(new URL('./image_timing.ts',import.meta.url)),input,
  ()=>project(input.notes,input.geometry));
}
