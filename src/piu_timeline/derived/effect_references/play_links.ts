/** Informational image corroboration. Never moves targets or invents switch clocks. */
export function links(data,events) {
 const notes=data.notes??[],processing=data.visual_channels?.processing?.notes??[];
 const holds=[...(data.hold_analysis?.holds??[]),...(data.hold_analysis?.unresolved_tracks??[]).map(t=>({...t,start_range:[t.visible_start_seconds??-Infinity]}))];
 return events.map(event=>{
  const [lo,hi]=event.observation_range;
  const candidates=[];
  notes.forEach((n,note)=>{
   if(n.lane!==event.lane)return;
   const points=n.points??[],start=n.visible_start_seconds??points[0]?.[0],end=n.visible_end_seconds??points.at(-1)?.[0];
   if(!Number.isFinite(start)||!Number.isFinite(end)||start>hi||end+.15<lo)return;
   candidates.push({note,note_type:n.note_type??'unknown',visibility_range:[start,end],
    processing:(processing.find(p=>p.note===note)?.status??null)});
  });
  const popup=(data.judgment_events??[]).flatMap((p,index)=>p.lower_seconds<=hi&&p.upper_seconds>=lo?[{index,label:p.label,range:[p.lower_seconds,p.upper_seconds]}]:[]);
  const holdRisk=holds.some(h=>h.lane===event.lane&&(h.start_range?.[0]??-Infinity)<=hi&&(h.end_range?.[1]??Infinity)>=lo);
  const other=events.some(e=>e!==event&&e.lane===event.lane&&e.observation_range[0]<=hi&&e.observation_range[1]>=lo);
  const unique=candidates.length===1&&candidates[0].note_type==='tap'&&!holdRisk&&!other;
  return {event:event.id,lane:event.lane,status:!['ordered_image_correspondence','ordered_image_candidate'].includes(event.status)?(event.status==='appearance_only_phase_unresolved'?'image_phase_unresolved':'no_image_correspondence'):
    unique?'unique_tap_image_candidate':holdRisk?'hold_context':other?'overlapping_effect_windows':candidates.length?'ambiguous_note_candidates':'unassigned',
    candidates,popup_candidates:popup,observation_range:event.observation_range,physical_input_range:null};
 });
}
