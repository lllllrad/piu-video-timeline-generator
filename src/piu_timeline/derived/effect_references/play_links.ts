/** Informational image corroboration. Never moves targets or invents switch clocks. */
import {intervals,lanes} from './intervals.ts';
export function links(data,events) {
 const notes=data.notes??[],processing=data.visual_channels?.processing?.notes??[];
 const holds=[...(data.hold_analysis?.holds??[]),...(data.hold_analysis?.unresolved_tracks??[]).map(t=>({...t,start_range:[t.visible_start_seconds??-Infinity]}))];
 const statuses=new Map();for(const p of processing)if(!statuses.has(p.note))statuses.set(p.note,p.status);
 const visible=notes.flatMap((n,note)=>{
  const points=n.points??[],start=n.visible_start_seconds??points[0]?.[0],end=n.visible_end_seconds??points.at(-1)?.[0];
  return Number.isFinite(start)&&Number.isFinite(end)?[{lane:n.lane,note,note_type:n.note_type??'unknown',visibility_range:[start,end],processing:statuses.get(note)??null}]:[];
 });
 const noteIndex=lanes(visible,n=>[n.visibility_range[0],n.visibility_range[1]+.15]);
 const popupIndex=intervals((data.judgment_events??[]).map((p,index)=>({index,label:p.label,range:[p.lower_seconds,p.upper_seconds]})),p=>p.range);
 const holdIndex=lanes(holds,h=>[h.start_range?.[0]??-Infinity,h.end_range?.[1]??Infinity]);
 const eventIndex=lanes(events,e=>e.observation_range);
 return events.map(event=>{
  const [lo,hi]=event.observation_range;
  const candidates=noteIndex(event.lane,lo,hi).map(({lane,...candidate})=>candidate);
  const popup=popupIndex(lo,hi);
  const holdRisk=holdIndex(event.lane,lo,hi).length>0;
  const other=eventIndex(event.lane,lo,hi).some(e=>e!==event);
  const unique=candidates.length===1&&candidates[0].note_type==='tap'&&!holdRisk&&!other;
  return {event:event.id,lane:event.lane,status:!['ordered_image_correspondence','ordered_image_candidate'].includes(event.status)?(event.status==='appearance_only_phase_unresolved'?'image_phase_unresolved':'no_image_correspondence'):
    unique?'unique_tap_image_candidate':holdRisk?'hold_context':other?'overlapping_effect_windows':candidates.length?'ambiguous_note_candidates':'unassigned',
    candidates,popup_candidates:popup,observation_range:event.observation_range,physical_input_range:null};
 });
}
