/** Recover a uniquely owned synchronized refresh using acquired target bounds. */
import {synchronizedRefreshes} from './association.ts';
import {targetInWindow} from './candidates.ts';
import {bracket,disputedRefresh} from './evidence.ts';
import type {RecordData} from './types.ts';

export function boundedRefreshes(data:RecordData,choices:RecordData,events:RecordData[],holdRisk:(lo:number,hi:number)=>boolean):RecordData[]{
 const matches=data.matches??[],notes=data.notes??[],delay=(data.display_delay_correction_ms??0)/1000;
 const assigned=new Set([...matches.map(m=>m.note),...(data.miss_candidates??[]).map(m=>m.note)]);
 const words=(data.judgment_events??[]).map(e=>({...e,status:e.detection_status==='excluded'||e.label==='MISS'?'excluded':'candidate'}));
 const result=[];
 for(const[ji,ci]of synchronizedRefreshes(data,words)){
  const owners=matches.filter(m=>m.combo_event===ci||m.judgment_event===ji);
  if(owners.some(m=>m.combo_event!==ci||m.judgment_event!==ji))continue;
  const c=data.combo_events[ci],j=words[ji];
  if(!['PERFECT','GREAT','GOOD','BAD'].includes(j.label)||c.upper_seconds-c.lower_seconds>.1+1e-6||
    j.anchor_combo_event!=null&&j.anchor_combo_event!==ci)continue;
  const lo=Math.min(c.lower_seconds,j.lower_seconds),hi=Math.max(c.upper_seconds,j.upper_seconds);
  if(holdRisk(lo,hi))continue;
  const compatible=notes.flatMap((n,i)=>n.status==='estimated'&&targetInWindow(n,c.lower_seconds,c.upper_seconds,delay)&&
    targetInWindow(n,j.lower_seconds,j.upper_seconds,delay)?[i]:[]);
  const pending=compatible.filter(i=>!assigned.has(i));
  if(!pending.length||owners.some(m=>!compatible.includes(m.note))||compatible.some(i=>assigned.has(i)&&!owners.some(m=>m.note===i)||notes[i].type_status!=='tap'||notes[i].note_type==='hold'||
    notes[i].timing_reconstruction?.status!=='restored'||!(notes[i].prediction_uncertainty_seconds>0)))continue;
  // Chords need one established row and distinct lanes, not just nearby centers.
  const target=notes[compatible[0]].target_seconds;
  if(compatible.some(i=>Math.abs(notes[i].target_seconds-target)>1e-8)||new Set(compatible.map(i=>notes[i].lane)).size!==compatible.length)continue;
  if(pending.some(i=>{
   const options=choices[i]??[];
   return ![['combo',ci],['judgment',ji]].every(([source,index])=>options.some(o=>o.source===source&&o.event===index&&o.alternative_rows===1))||
    events.some(e=>!(e.source==='combo'&&e.event===ci||e.source==='judgment'&&e.event===ji)&&
     !matches.some(m=>m[e.source==='combo'?'combo_event':'judgment_event']===e.event)&&
     targetInWindow(notes[i],e.lower_seconds,e.upper_seconds,delay));
  }))continue;
  if(matches.some(m=>{const[a,b]=bracket(m);return a!=null&&b!=null&&(b<lo&&m.target_seconds>target||a>hi&&m.target_seconds<target);}))continue;
  const range=[Math.max(...compatible.map(i=>notes[i].target_seconds-notes[i].prediction_uncertainty_seconds),c.lower_seconds-.045-delay,j.lower_seconds-.045-delay),
   Math.min(...compatible.map(i=>notes[i].target_seconds+notes[i].prediction_uncertainty_seconds),c.upper_seconds+.045-delay,j.upper_seconds+.045-delay)];
  if(range[0]>range[1]||compatible.some(i=>disputedRefresh(data,i,[{...c,source:'combo',event:ci},{...j,source:'judgment',event:ji}])))continue;
  for(const i of pending){
   result.push({note:i,target_seconds:notes[i].target_seconds,row_note_count:compatible.length,aggregate_row_count:1,
    combo_event:ci,judgment_event:ji,judgment_label:j.label,judgment_label_source:'synchronized_refresh',evidence_source:'combo+judgment',
    combo_lower_seconds:c.lower_seconds,combo_upper_seconds:c.upper_seconds,observation_lower_seconds:c.lower_seconds,observation_upper_seconds:c.upper_seconds,
    raw_offset_lower_ms:1000*(c.lower_seconds-notes[i].target_seconds),raw_offset_upper_ms:1000*(c.upper_seconds-notes[i].target_seconds),
    recovery_method:'exclusive_bounded_target_with_synchronized_refreshes',association_target_range:range,
    source_target_range:[notes[i].target_seconds-notes[i].prediction_uncertainty_seconds,notes[i].target_seconds+notes[i].prediction_uncertainty_seconds]});
   assigned.add(i);
  }
 }
 return result;
}
