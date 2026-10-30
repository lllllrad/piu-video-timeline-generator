/** Immutable stage results. Only composition adapters build a combined read model. */
export type Immutable<T> = T extends (...args: never[]) => unknown ? T : T extends object ? {readonly [K in keyof T]:Immutable<T[K]>}:T;
export interface Artifact<Kind extends string, Data> {readonly schema:1; readonly stage:Kind; readonly data:Immutable<Data>}
export type Evidence = Readonly<Record<string,unknown>>;
export type Point = readonly [number,number];
export interface ObservedNote {note:number;lane:number;detection_points:readonly Point[];attributes:Evidence;separate_detection_trajectory:boolean}
export interface Geometry {analysis_width?:number;analysis_height?:number;layout?:Evidence;start_seconds?:number;end_seconds?:number}
export interface TrackObservations {notes:readonly ObservedNote[];geometry:Geometry}
export type ObservationArtifact=Artifact<'track-observations',TrackObservations>;
export const coordinateFields=['points','status','reason','target_seconds','prediction_uncertainty_seconds','velocity_pixels_per_second',
 'residual_pixels','speed_change_fraction','fit_method','motion_clock','motion_target_phase','clock_target_phase','motion_chunk','motion_support_points',
 'observed_phase_slope','head_registration','timing_reconstruction','native_clock_warning','rejected_chunk_clock','stationary_phase_interval',
 'crossing_source_pts_seconds','crossing_frame_seconds','crossing_capture_range','validated_later_observations','later_observation_maximum_error_pixels',
 'later_observation_tolerance_pixels','extrapolation_seconds','motion_support_end_seconds'] as const;
export type CoordinateValues=Partial<Record<typeof coordinateFields[number],unknown>>;
export interface CoordinateNote {note:number;values:CoordinateValues}
export interface CoordinateResult {notes:readonly CoordinateNote[];scroll_motion?:Evidence;head_registration?:Evidence;timing_reconstruction?:Evidence}
export type CoordinateArtifact=Artifact<'coordinates',CoordinateResult>;
export const beatFields=['status','reason','target_seconds','prediction_uncertainty_seconds','video_target_range','beat_reconstruction',
 'timing_reconstruction','fit_method','native_clock_warning'] as const;
export type BeatValues=Partial<Record<typeof beatFields[number],unknown>>;
export interface ResultNote {note:number;values:Readonly<Record<string,unknown>>;removed:readonly string[]}
export const nativeTimingFields=coordinateFields.filter(k=>!['points','head_registration'].includes(k));
export interface NativeTimingResult {notes:readonly ResultNote[];timing_reconstruction?:Evidence}
export type NativeTimingArtifact=Artifact<'native-timing',NativeTimingResult>;
export interface BeatResult {notes:readonly ResultNote[];beat_timing:Evidence;native_recovery?:Evidence}
export type BeatArtifact=Artifact<'beats',BeatResult>;
export interface CoordinateSource {observations:ObservationArtifact;coordinates:CoordinateArtifact}
export interface BeatReference {
 status:'available'|'unavailable';reason?:string;song_start_seconds?:number;alignment_uncertainty_seconds?:number;
 constant_tempo_bpm?:string|number|null;timing?:string;sha256?:string;ucs_index?:string;metadata_path?:string;
}
export interface BeatRequest extends CoordinateSource {schema:1;native_timing:NativeTimingArtifact;reference:BeatReference;timing_text:string|null;preparation?:Evidence|null}

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
 if(!v||v.schema!==1||v.stage!==kind||!v.data||typeof v.data!=='object'||Array.isArray(v.data)||Object.keys(v).some(k=>!['schema','stage','data'].includes(k)))
  throw new Error(`Expected ${kind} stage artifact`);
}
