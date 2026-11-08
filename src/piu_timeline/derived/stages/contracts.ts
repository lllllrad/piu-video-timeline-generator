/** Immutable stage results. Only composition adapters build a combined read model. */
import {fingerprint} from '../fingerprint.ts';
export type Immutable<T> = T extends (...args: never[]) => unknown ? T : T extends object ? {readonly [K in keyof T]:Immutable<T[K]>}:T;
export interface Artifact<Kind extends string, Data> {readonly schema:1; readonly stage:Kind; readonly data:Immutable<Data>;readonly input_fingerprint?:string;readonly artifact_root?:string}
export interface BoundArtifact<Kind extends string,Data> extends Artifact<Kind,Data> {readonly input_fingerprint:string}
export type Evidence = Readonly<Record<string,unknown>>;
export type Point = readonly [number,number];
export interface ObservedNote {note:number;lane:number;detection_points:readonly Point[];attributes:Evidence;separate_detection_trajectory:boolean}
export interface Geometry {analysis_width?:number;analysis_height?:number;layout?:Evidence;start_seconds?:number;end_seconds?:number}
export interface TrackObservations {notes:readonly ObservedNote[];geometry:Geometry;timeline:readonly {time:number;source_pts:number}[]}
export type ObservationArtifact=Artifact<'track-observations',TrackObservations>;
export const physicalFields=['coordinate_bridge','crossing_method','duplicate_of','status','reason','target_seconds','prediction_uncertainty_seconds','velocity_pixels_per_second',
 'native_interval_model','native_motion_support','residual_pixels','speed_change_fraction','fit_method','motion_clock','motion_clock_validation','motion_target_phase','clock_target_phase','motion_chunk','motion_support_points',
 'observed_phase_slope','timing_reconstruction','native_clock_warning','rejected_chunk_clock','stationary_phase_interval',
 'crossing_source_pts_seconds','crossing_frame_seconds','crossing_capture_range','validated_later_observations','later_observation_maximum_error_pixels',
 'later_observation_tolerance_pixels','extrapolation_seconds','motion_support_end_seconds'] as const;
export const coordinateFields=['points','head_registration'] as const;
export type CoordinateValues=Partial<Record<typeof coordinateFields[number],unknown>>;
export interface CoordinateNote {note:number;values:CoordinateValues}
export interface CoordinateResult {notes:readonly CoordinateNote[];head_registration?:Evidence}
export type CoordinateArtifact=BoundArtifact<'coordinates',CoordinateResult>;
export const beatFields=['status','reason','target_seconds','prediction_uncertainty_seconds','video_target_range','beat_reconstruction',
 'timing_reconstruction','fit_method','native_clock_warning'] as const;
export type BeatValues=Partial<Record<typeof beatFields[number],unknown>>;
export interface ResultNote {note:number;values:Readonly<Record<string,unknown>>;removed:readonly string[]}
export const nativeTimingFields=['status','reason','target_seconds','prediction_uncertainty_seconds',
 'fit_method','native_clock_warning','crossing_method','timing_reconstruction'] as const;
export interface PhysicalTimingResult {notes:readonly {note:number;values:Partial<Record<typeof physicalFields[number],unknown>>}[];scroll_motion?:Evidence;timing_reconstruction?:Evidence}
export type PhysicalTimingArtifact=BoundArtifact<'physical-timing',PhysicalTimingResult>;
export interface TimingSource extends CoordinateSource {physical_timing:PhysicalTimingArtifact}
export interface NativeTimingResult {notes:readonly ResultNote[];timing_reconstruction?:Evidence}
export type NativeTimingArtifact=BoundArtifact<'native-timing',NativeTimingResult>;
export interface BeatResult {notes:readonly ResultNote[];beat_timing:Evidence;native_recovery?:Evidence}
export type BeatArtifact=BoundArtifact<'beats',BeatResult>;
export interface CoordinateSource {observations:ObservationArtifact;coordinates:CoordinateArtifact}
export interface BeatReference {
 status:'available'|'unavailable';reason?:string;song_start_seconds?:number;alignment_uncertainty_seconds?:number;
 alignment_method?:string|null;
 constant_tempo_bpm?:string|number|null;timing?:string;sha256?:string;ucs_index?:string;metadata_path?:string;
}
export interface BeatRequest extends TimingSource {schema:1;native_timing:NativeTimingArtifact;reference:BeatReference;timing_text:string|null;preparation?:Evidence|null}

function freeze<T>(value:T):Immutable<T>{
 if(value&&typeof value==='object'&&!Object.isFrozen(value)){
  Object.values(value).forEach(v=>freeze(v));Object.freeze(value);
 }
 return value as Immutable<T>;
}
export function artifact<K extends string,T>(stage:K,data:T):Artifact<K,T>{
 return Object.freeze({schema:1 as const,stage,data:freeze(structuredClone(data))});
}
export function requireArtifact<K extends string>(value:unknown,kind:K):asserts value is Artifact<K,unknown>{
 const v=value as {schema?:unknown;stage?:unknown;data?:unknown};
 if(!v||v.schema!==1||v.stage!==kind||!v.data||typeof v.data!=='object'||Array.isArray(v.data)||Object.keys(v).some(k=>!['schema','stage','data','input_fingerprint','artifact_root'].includes(k)))
  throw new Error(`Expected ${kind} stage artifact`);
}

/** Root is explicit so directory promotion preserves input identity without hiding path dependencies. */
export function boundArtifact<K extends string,T>(stage:K,input:unknown,data:T,root?:string):BoundArtifact<K,T>{
 const artifactRoot=root?root.replace(/\/+$/,'')+'/':undefined;
 return Object.freeze({...artifact(stage,data),input_fingerprint:fingerprint(input,artifactRoot),
  ...(artifactRoot?{artifact_root:artifactRoot}:{})});
}
export function requireInput<K extends string>(value:Artifact<K,unknown>,input:unknown):void{
 if(value.artifact_root!==undefined&&(typeof value.artifact_root!=='string'||!value.artifact_root.endsWith('/')))
  throw new Error(`Invalid artifact root for ${value.stage}`);
 if(typeof value.input_fingerprint!=='string'||value.input_fingerprint!==fingerprint(input,value.artifact_root))
  throw new Error(`${value.stage} result belongs to different inputs`);
}
