/** Read-model composition is the only place stage views are combined. */
import {artifact,requireArtifact,type Evidence} from '../stages/contracts.ts';
import {changes,apply,type NotePatch} from '../stages/notes.ts';
import {calculationView,type InspectionSource,type ViewArtifact,type ViewStage,type InspectionArtifact,type InterpretationArtifact} from './contracts.ts';
import type {RecordData} from '../types.ts';
const noteFields=['status','reason','target_seconds','prediction_uncertainty_seconds','type_status','type_evidence','type_unknown_reasons',
 'note_type','hold_cap_role','observed_hold_head','hold_id','input_requirement','requires_head_press','chart_timing_status','target_timing_basis','geometry_native_range','geometry_source_failure'];
const fields={
 'configured-processing':['visual_channels'],
 'hold-view':['matches','limitations','excluded_notes','miss_candidates','combo_events','judgment_events','hold_tick_ambiguous_notes','recovered_pre_hold_notes','recovered_dense_notes',
  'recovered_lane_supported_notes','recovered_bounded_target_notes','hold_analysis','coverage','note_type_diagnostics','conflicted_matches','association_view_format'],
 'motion-effects':['scroll_pause_model','scroll_speed_model'],
 'effect-view':['combo_events','matches','coverage','conflicted_matches','association_view_format','object_interpretation','chart_policy','visual_channels'],
 'policy-view':['matches','miss_candidates','hold_analysis','coverage'],
 'timing-ranges':['timing_ranges'],visibility:['visibility_diagnostics'],diagnostics:['exclusion_diagnostics','recognition_diagnostics'],
} as const;
export function result(stage:ViewStage,before:RecordData,patch:RecordData):ViewArtifact{
 const allowed=fields[stage] as readonly string[];
 if(Object.keys(patch).some(k=>k!=='notes'&&!allowed.includes(k)))throw new Error(`Unowned output from ${stage}`);
 const updates=patch.notes?changes(before.notes??[],patch.notes.slice(0,(before.notes??[]).length),stage==='hold-view'?noteFields:[]):[];
 const added=patch.notes?.slice((before.notes??[]).length)??[];
 if(added.length&&stage!=='hold-view')throw new Error(`Unexpected chart objects from ${stage}`);
 const data={...Object.fromEntries(Object.entries(patch).filter(([k])=>k!=='notes')),note_updates:updates,derived_notes:added};
 return artifact(stage,data);
}
export function applyResult(before:RecordData,value:ViewArtifact):RecordData{
 requireArtifact(value,value.stage);
 if(!Object.hasOwn(fields,value.stage))throw new Error('Unknown inspection stage');
 const {note_updates,derived_notes,...patch}=value.data;
 if(Object.keys(patch).some(k=>!(fields[value.stage]as readonly string[]).includes(k)))throw new Error(`Unowned output from ${value.stage}`);
 const notes=apply(before.notes??[],note_updates as unknown as NotePatch[],value.stage==='hold-view'?noteFields:[]);
 if((derived_notes as unknown[]).length&&value.stage!=='hold-view')throw new Error('Foreign derived chart objects');
 const owned=structuredClone(patch) as RecordData;
 if(value.stage==='policy-view'&&owned.hold_analysis)owned.hold_analysis={...before.hold_analysis,...owned.hold_analysis};
 if(owned.visual_channels){
  if(!before.visual_channels)delete owned.visual_channels;
  else owned.visual_channels={...before.visual_channels,...Object.fromEntries(Object.entries(owned.visual_channels).filter(([,v])=>v!==undefined).map(([name,value])=>{
   const channel={...before.visual_channels[name],...value as RecordData};
   if(name==='processing'&&channel.notes){
    const original=new Map((before.visual_channels.processing?.notes??[]).map(n=>[n.note,n]));
    channel.notes=channel.notes.map(n=>{const {sample_count,...view}=n;return {...original.get(n.note)as RecordData,...view};});
   }
   return [name,channel];
  }))};
 }
 return {...before,...owned,notes:[...notes,...structuredClone(derived_notes as unknown[])]};
}
export function materialize(request:{source:InspectionSource},value:InspectionArtifact|InterpretationArtifact):RecordData{
 requireArtifact(value,value.stage);
 if(!['inspection','interpretation'].includes(value.stage))throw new Error('Expected an inspection or interpretation result');
 let data=calculationView(request.source);
 const expected=value.stage==='interpretation'?['hold-view','motion-effects']:['hold-view','motion-effects',...(value.data.stages.some(s=>s.stage==='configured-processing')?['configured-processing']:[]),'effect-view','policy-view','timing-ranges','visibility','diagnostics'];
 if(value.data.stages.length!==expected.length||value.data.stages.some((s,i)=>s.stage!==expected[i]))throw new Error('Incomplete or out-of-order inspection stages');
 const seen=new Set<string>();
 for(const stage of value.data.stages){if(seen.has(stage.stage))throw new Error('Duplicate inspection stage');seen.add(stage.stage);data=applyResult(data,stage);}
 return {...structuredClone(request.source.metadata),...data};
}
