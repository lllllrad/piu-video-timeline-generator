/** Saved physical artifacts -> prepared beat descriptor -> independent beat result -> read model. */
import {resolve}from 'node:path';
import {createHash}from 'node:crypto';
import {stage,requireIdentity}from '../pipeline/file_stage.ts';
import {implementation}from '../pipeline/store.ts';
import {InputFiles,type FileIdentity}from '../pipeline/input_files.ts';
import {read as physical}from '../stages/timing_files.ts';
import {input,reconstruct,materialize,type BeatInput}from './stage.ts';
import type {RecordData}from '../types.ts';
interface Reference extends FileIdentity {path:string}
interface Prepared extends RecordData {schema:2;inputs:{coordinates:Reference;physical:Reference;native:Reference};timing:Reference|null}
const names={coordinates:'coordinates.json',physical:'physical-timing.json',native:'native-timing.json'};
function descriptor(files:InputFiles):Prepared{
 const value=files.json<Prepared>('beat-input.json');
 if(value.schema!==2||!value.inputs||!value.reference)throw Error('Invalid prepared beat file descriptor');
 for(const [key,name]of Object.entries(names))if(value.inputs[key]?.path!==name)throw Error('Invalid beat dependency path');
 return value;
}
function dependencies(files:InputFiles):string[]{
 const value=descriptor(files);return [...Object.values(names),...(value.timing?[value.timing.path]:[])];
}
function request(files:InputFiles):BeatInput{
 const value=descriptor(files);
 for(const ref of Object.values(value.inputs))requireIdentity(files,ref.path,ref);
 let text:string|null=null;
 if(value.timing){
  requireIdentity(files,value.timing.path,value.timing);text=files.text(value.timing.path);
  if(createHash('sha256').update(text).digest('hex')!==value.reference.sha256)throw Error('Official timing file fingerprint mismatch');
 }else if(value.reference.status==='available')throw Error('Available musical reference has no timing file');
 return input(physical(files),files.json('native-timing.json'),value.reference,text,value.preparation);
}
export function prepare(directory:string){
 return stage(directory,'beat-input',implementation(new URL('./files.ts',import.meta.url)),
  ['beat-reference.json',...Object.values(names)],'beat-input.json',files=>{
   const source=files.json('beat-reference.json');
   if(source.schema!==1||!source.reference)throw Error('Invalid prepared musical reference');
   const timing=source.reference.status==='available'?resolve(source.reference.timing):null;
   if(timing&&createHash('sha256').update(files.text(timing)).digest('hex')!==source.reference.sha256)
    throw Error('Official timing file fingerprint mismatch');
   return {schema:2,inputs:Object.fromEntries(Object.entries(names).map(([key,path])=>[key,{path,...files.identity(path)}])),
    reference:source.reference,timing:timing?{path:timing,...files.identity(timing)}:null,...(source.preparation?{preparation:source.preparation}:{})};
  },files=>{const source=files.json('beat-reference.json');return source.reference?.status==='available'?[resolve(source.reference.timing)]:[];});
}
export function calculate(directory:string){
 return stage(directory,'musical-timing',implementation(new URL('./files.ts',import.meta.url)),['beat-input.json'],'beat-result.json',
  files=>reconstruct(request(files)),dependencies);
}
export function view(directory:string){
 return stage(directory,'timed-view',implementation(new URL('./files.ts',import.meta.url)),['beat-input.json','beat-result.json'],'timed-view.json',
  files=>materialize(request(files),files.json('beat-result.json')),dependencies);
}
