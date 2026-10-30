/** Coordinates -> musical timing. The result owns timing decisions, never observations. */
import {reconstruct as calculate} from './reconstruct.ts';
import {artifact,requireArtifact,beatFields,type BeatArtifact,type BeatRequest,type BeatReference,type Evidence,type CoordinateSource,type NativeTimingArtifact} from '../stages/contracts.ts';
import {materialize as nativeView} from '../stages/native_timing.ts';
import {changes,apply} from '../stages/notes.ts';
import type {RecordData} from '../types.ts';
export type BeatInput=BeatRequest;

/** Wire adapter used only at acquisition/CLI boundaries. */
export function input(source:CoordinateSource,native_timing:NativeTimingArtifact,reference:BeatReference,timing_text:string|null,preparation?:Evidence|null):BeatInput{
 return {schema:1,...source,native_timing,reference,timing_text,...(preparation?{preparation}: {})};
}
export function reconstruct(request:BeatInput):BeatArtifact{
 if(request?.schema!==1)throw new Error('Unsupported beat-stage input schema');
 requireArtifact(request.observations,'track-observations');requireArtifact(request.coordinates,'coordinates');
 const data=nativeView(request,request.native_timing),result=calculate({schema:1,data,reference:structuredClone(request.reference),
  timing_text:request.timing_text,preparation:structuredClone(request.preparation)});
 return artifact('beats',{beat_timing:result.beat_timing,
  notes:changes(data.notes,result.notes??data.notes,beatFields),
  ...(result.timing_reconstruction?{native_recovery:result.timing_reconstruction}: {})});
}

/** Explicit read-model composition. Stage artifacts and their observations stay unchanged. */
export function materialize(request:BeatInput,result:BeatArtifact):RecordData{
 requireArtifact(result,'beats');const base=nativeView(request,request.native_timing);
 return {...base,beat_timing:structuredClone(result.data.beat_timing),
  ...(result.data.native_recovery?{timing_reconstruction:structuredClone(result.data.native_recovery)}: {}),
  notes:apply(base.notes,result.data.notes,beatFields)};
}
