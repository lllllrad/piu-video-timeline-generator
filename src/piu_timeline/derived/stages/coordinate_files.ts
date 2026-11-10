/** Native registered observations -> persisted coordinates. No timing data crosses this boundary. */
import {InputFiles}from '../pipeline/input_files.ts';
import {stage}from '../pipeline/file_stage.ts';
import {fingerprint,implementation}from '../pipeline/store.ts';
import {capture,materialize}from './coordinates.ts';
import type {CoordinateSource}from './contracts.ts';
import type {RecordData}from '../types.ts';
import {contracts}from '../contracts.ts';
export const FORMAT=contracts.coordinate_artifact;
export function read(files:InputFiles):CoordinateSource{
 const value=files.json('coordinates.json'),{fingerprint:digest,...payload}=value;
 if(fingerprint(value.format)!==fingerprint(FORMAT))throw Error('Unsupported coordinate artifact format');
 if(digest!==fingerprint(payload,files.root))throw Error('Stored coordinate artifact fingerprint mismatch');
 return value.output;
}
export function save(directory:string){
 return stage(directory,'coordinates',implementation(new URL('./coordinate_files.ts',import.meta.url)),['coordinate-input.json'],'coordinates.json',files=>{
  const input=files.json('coordinate-input.json');
  if(input.schema!==1||!input.identity||!input.data)throw Error('Invalid registered-coordinate input');
  const payload={format:FORMAT,identity:input.identity,output:capture(input.data,files.root)};
  return {...payload,fingerprint:fingerprint(payload,files.root)};
 },undefined,value=>({format:FORMAT,fingerprint:value.fingerprint})).metadata;
}
export function inspect(directory:string,expected:RecordData,identity:RecordData){
 const files=new InputFiles(directory,['coordinates.json']);files.seal();read(files);
 const payload=files.json('coordinates.json');
 if(payload.fingerprint!==expected.fingerprint)throw Error('Stored coordinate artifact fingerprint differs from analysis');
 if(fingerprint(payload.identity,files.root)!==fingerprint(identity,files.root))return null;
 files.verify();return expected;
}
export function view(directory:string){
 return stage(directory,'coordinate-view',implementation(new URL('./coordinate_files.ts',import.meta.url)),['coordinates.json'],'coordinate-view.json',files=>materialize(read(files)));
}
