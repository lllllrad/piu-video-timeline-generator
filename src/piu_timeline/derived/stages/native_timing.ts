/** Physical endpoint validation depends only on coordinates and source image proof. */
import {resolve as validateGaps} from '../native_gaps.ts';
import {boundArtifact,requireArtifact,requireInput,nativeTimingFields,type TimingSource,type NativeTimingArtifact} from './contracts.ts';
import {materialize as coordinateView} from './physical_timing.ts';
import {changes,apply} from './notes.ts';
import type {RecordData} from '../types.ts';
const inputOf=(source:TimingSource):TimingSource=>({observations:source.observations,coordinates:source.coordinates,physical_timing:source.physical_timing});
export function resolve(source:TimingSource):NativeTimingArtifact{
 const data=coordinateView(source),result=validateGaps(data);
 return boundArtifact('native-timing',inputOf(source),{notes:changes(data.notes,result.notes??data.notes,nativeTimingFields),
  ...(result.timing_reconstruction?{timing_reconstruction:result.timing_reconstruction}: {})},source.coordinates.artifact_root);
}
export function materialize(source:TimingSource,result:NativeTimingArtifact):RecordData{
 requireArtifact(result,'native-timing');requireInput(result,inputOf(source));
 if(Object.keys(result.data).some(k=>!['notes','timing_reconstruction'].includes(k)))throw Error('Foreign native timing fields');
 const data=coordinateView(source);
 return {...data,...(result.data.timing_reconstruction?{timing_reconstruction:structuredClone(result.data.timing_reconstruction)}: {}),
  notes:apply(data.notes,result.data.notes,nativeTimingFields)};
}
