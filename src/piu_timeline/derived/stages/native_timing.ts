/** Physical endpoint validation depends only on coordinates and source image proof. */
import {resolve as validateGaps} from '../native_gaps.ts';
import {artifact,requireArtifact,nativeTimingFields,type CoordinateSource,type NativeTimingArtifact} from './contracts.ts';
import {materialize as coordinateView} from './coordinates.ts';
import {changes,apply} from './notes.ts';
import type {RecordData} from '../types.ts';
export function resolve(source:CoordinateSource):NativeTimingArtifact{
 const data=coordinateView(source),result=validateGaps(data);
 return artifact('native-timing',{notes:changes(data.notes,result.notes??data.notes,nativeTimingFields),
  ...(result.timing_reconstruction?{timing_reconstruction:result.timing_reconstruction}: {})});
}
export function materialize(source:CoordinateSource,result:NativeTimingArtifact):RecordData{
 requireArtifact(result,'native-timing');const data=coordinateView(source);
 return {...data,...(result.data.timing_reconstruction?{timing_reconstruction:structuredClone(result.data.timing_reconstruction)}: {}),
  notes:apply(data.notes,result.data.notes,nativeTimingFields)};
}
