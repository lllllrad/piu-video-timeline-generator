/** Stage input scopes: passive document metadata never enters inference. */
import {artifact,requireArtifact,type Artifact,type Evidence,type Immutable} from '../stages/contracts.ts';
import type {RecordData} from '../types.ts';
export const scopes={
 tracks:['notes','layout','analysis_width','analysis_height','head_registration','scroll_motion','timing_reconstruction','beat_timing','start_seconds','end_seconds','skin_detector'],
 judgments:['matches','conflicted_matches','miss_candidates','combo_events','judgment_events','counter_frame_events','counter_judgment_labels','display_delay_correction_ms','median_frame_interval_seconds',
  'unsupported_intervals','coverage','excluded_notes','limitations','deferred_matches','association_view_format','hold_tick_ambiguous_notes','recovered_pre_hold_notes','recovered_dense_notes','recovered_lane_supported_notes','recovered_bounded_target_notes'],
 holds:['hold_analysis','note_type_diagnostics','skin_role_evidence','body_risk_evidence'],
 context:['chart_policy','object_interpretation','visual_support','scroll_pause_model','scroll_speed_model'],
 channels:['visual_channels'],
} as const;
type Selection<T extends readonly string[]>={readonly [K in T[number]]?:unknown};
export interface InspectionSource {
 tracks:Artifact<'inspection-tracks',Selection<typeof scopes.tracks>>;
 judgments:Artifact<'judgment-associations',Selection<typeof scopes.judgments>>;
 holds:Artifact<'hold-evidence',Selection<typeof scopes.holds>>;
 context:Artifact<'chart-context',Selection<typeof scopes.context>>;
 channels:Artifact<'visual-channels',Selection<typeof scopes.channels>>;
 metadata:Evidence;
}
const kinds={tracks:'inspection-tracks',judgments:'judgment-associations',holds:'hold-evidence',context:'chart-context',channels:'visual-channels'} as const;
export function capture(data:RecordData):InspectionSource{
 const known=new Set<string>(Object.values(scopes).flat());
 return {...Object.fromEntries(Object.entries(scopes).map(([key,fields])=>[key,artifact(kinds[key],Object.fromEntries(fields.filter(k=>Object.hasOwn(data,k)).map(k=>[k,data[k]])))])),
  metadata:structuredClone(Object.fromEntries(Object.entries(data).filter(([k])=>!known.has(k))))} as InspectionSource;
}
export function calculationView(source:InspectionSource):RecordData{
 const result:RecordData={};
 for(const [scope,kind]of Object.entries(kinds)){
  const value=source[scope];requireArtifact(value,kind);
  if(Object.keys(value.data).some(k=>!scopes[scope].includes(k)))throw new Error(`Foreign fields in ${kind} input`);
  Object.assign(result,structuredClone(value.data));
 }
 return result;
}
export interface CounterFrame {playback_seconds:number;source_pts_seconds:number;combo?:number|null;combo_confidence?:number}
export interface VisibilityFrame {playback_seconds:number;source_pts_seconds:number;notes?:readonly {lane:number;x:number;y:number}[]}
export interface PreparedObservations {
 frames:readonly CounterFrame[];visibility_frames:readonly VisibilityFrame[];occluders:readonly Evidence[];
 native_body_risk_available:boolean;pre_hold_proofs:Readonly<Record<string,Evidence>>;
 configured_processing?:{input:Evidence;output:Evidence};source_artifacts?:Readonly<Record<string,readonly[number,number|bigint]|null>>;
}
export interface PresentationInput {schema:2;source:InspectionSource;observations:Immutable<PreparedObservations>}
export type ViewStage='configured-processing'|'hold-view'|'motion-effects'|'effect-view'|'policy-view'|'timing-ranges'|'visibility'|'diagnostics';
export type ViewArtifact=Artifact<ViewStage,Evidence>;
export interface InspectionResult {stages:readonly ViewArtifact[]}
export type InspectionArtifact=Artifact<'inspection',InspectionResult>;
export type InterpretationArtifact=Artifact<'interpretation',InspectionResult>;
export function input(data:RecordData,observations:PreparedObservations):PresentationInput{return {schema:2,source:capture(data),observations};}
