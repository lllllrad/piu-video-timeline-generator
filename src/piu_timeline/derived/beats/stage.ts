/** Coordinates -> musical timing. The result owns timing decisions, never observations. */
import {Store,implementation,atomicJSON} from '../pipeline/store.ts';
import {resolve as resolvePath} from 'node:path';
import {reconstruct as calculate} from './reconstruct.ts';
import {boundArtifact,requireArtifact,requireInput,beatFields,type BeatArtifact,type BeatRequest,type BeatReference,type Evidence,type TimingSource,type NativeTimingArtifact} from '../stages/contracts.ts';
import {materialize as nativeView} from '../stages/native_timing.ts';
import {changes,apply} from '../stages/notes.ts';
import type {RecordData} from '../types.ts';
export type BeatInput=BeatRequest;

/** Wire adapter used only at acquisition/CLI boundaries. */
export function input(source:TimingSource,native_timing:NativeTimingArtifact,reference:BeatReference,timing_text:string|null,preparation?:Evidence|null):BeatInput{
 return {schema:1,observations:source.observations,coordinates:source.coordinates,physical_timing:source.physical_timing,native_timing,reference,timing_text,...(preparation?{preparation}: {})};
}
export function reconstruct(request:BeatInput):BeatArtifact{
 if(request?.schema!==1)throw new Error('Unsupported beat-stage input schema');
 requireArtifact(request.observations,'track-observations');requireArtifact(request.coordinates,'coordinates');
 const data=nativeView(request,request.native_timing),result=calculate({schema:1,data,reference:structuredClone(request.reference),
  timing_text:request.timing_text,preparation:structuredClone(request.preparation)});
 return boundArtifact('beats',request,{beat_timing:result.beat_timing,
  notes:changes(data.notes,result.notes??data.notes,beatFields),
  ...(result.timing_reconstruction?{native_recovery:result.timing_reconstruction}: {})},request.coordinates.artifact_root);
}

/** Explicit read-model composition. Stage artifacts and their observations stay unchanged. */
export function materialize(request:BeatInput,result:BeatArtifact):RecordData{
 requireArtifact(result,'beats');requireInput(result,request);
 if(Object.keys(result.data).some(k=>!['notes','beat_timing','native_recovery'].includes(k)))throw Error('Foreign beat fields');
 const base=nativeView(request,request.native_timing);
 return {...base,beat_timing:structuredClone(result.data.beat_timing),
  ...(result.data.native_recovery?{timing_reconstruction:structuredClone(result.data.native_recovery)}: {}),
  notes:apply(base.notes,result.data.notes,beatFields)};
}

/** Prepared beat inference has no counter or physical-switch input. */
export function saved(request:BeatInput,directory:string):BeatArtifact{
 const store=new Store(directory),result=store.run('musical-timing',implementation(new URL('./stage.ts',import.meta.url)),request,()=>reconstruct(request));
 materialize(request,result);atomicJSON(resolvePath(directory,'beat-result.json'),result);return result;
}
