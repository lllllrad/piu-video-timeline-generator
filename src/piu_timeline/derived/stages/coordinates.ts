/** Acquisition/read-model adapter. No combo, judgment or association belongs to coordinates. */
import {artifact,requireArtifact,coordinateFields,beatFields,type CoordinateSource,type CoordinateResult,type TrackObservations} from './contracts.ts';
import type {RecordData} from '../types.ts';
const pick=(v:RecordData,keys:readonly string[])=>Object.fromEntries(keys.filter(k=>Object.hasOwn(v,k)).map(k=>[k,v[k]]));

export function capture(source:RecordData):CoordinateSource{
 if(!Array.isArray(source.notes))throw new Error('Coordinate source requires observed notes');
 const owned=new Set<string>([...coordinateFields,...beatFields,'lane','detected_points']);
 const observations:TrackObservations={geometry:pick(source,['analysis_width','analysis_height','layout','start_seconds','end_seconds']),
  notes:source.notes.map((n,note)=>({note,lane:n.lane,separate_detection_trajectory:Object.hasOwn(n,'detected_points'),detection_points:n.detected_points??n.points,
   attributes:Object.fromEntries(Object.entries(n).filter(([k])=>!owned.has(k)))}))};
 const coordinates:CoordinateResult={...pick(source,['scroll_motion','head_registration','timing_reconstruction']),
  notes:source.notes.map((n,note)=>({note,values:pick(n,coordinateFields)}))};
 return {observations:artifact('track-observations',observations),coordinates:artifact('coordinates',coordinates)};
}

export function materialize(source:CoordinateSource):RecordData{
 requireArtifact(source.observations,'track-observations');requireArtifact(source.coordinates,'coordinates');
 if(Object.keys(source.coordinates.data).some(k=>!['notes','scroll_motion','head_registration','timing_reconstruction'].includes(k))||
  Object.keys(source.observations.data).some(k=>!['notes','geometry'].includes(k)))throw new Error('Foreign coordinate stage fields');
 const observed=source.observations.data.notes,fit=source.coordinates.data.notes;
 if(observed.length!==fit.length||observed.some((n,i)=>n.note!==i||fit[i].note!==i))throw new Error('Coordinate results have different observation identities');
 for(const n of fit)if(Object.keys(n.values).some(k=>!(coordinateFields as readonly string[]).includes(k)))throw new Error('Coordinate stage contains foreign note fields');
 return {...structuredClone(source.observations.data.geometry),...structuredClone(source.coordinates.data),
  notes:observed.map((n,i)=>({...structuredClone(n.attributes),lane:n.lane,...structuredClone(fit[i].values),
   ...(n.separate_detection_trajectory?{detected_points:structuredClone(n.detection_points)}:{})}))};
}
