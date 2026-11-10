/** Persist one producer output; cache hits never reconstruct numerical input objects. */
import {existsSync}from 'node:fs';
import {resolve}from 'node:path';
import {InputFiles,paths,type FileIdentity}from './input_files.ts';
import {atomicJSON,fingerprint}from './store.ts';
import type {RecordData}from '../types.ts';
export interface FileResult extends FileIdentity {path:string;reused:boolean;metadata?:RecordData}
export function stage(directory:string,name:string,producer:string,inputs:readonly string[],output:string,
 compute:(files:InputFiles)=>unknown,setup?:(files:InputFiles)=>readonly string[],summary?:(result:any)=>RecordData):FileResult{
 if(!/^[a-z][a-z-]*$/.test(name))throw Error('Invalid file stage name');
 const manifest=`file-stages/${name}.json`,files=new InputFiles(directory,inputs),extra=setup?.(files)??[];
 files.add(extra);const dependencies=[...new Set([...inputs,...extra])],
  binding={schema:1,stage:name,producer,inputs:files.identities(dependencies)},key=fingerprint(binding);
 if(existsSync(resolve(directory,manifest))){
  files.add([manifest]);const saved=files.json(manifest);
  const {fingerprint:digest,...document}=saved;
  if(saved.schema!==1||saved.stage!==name||digest!==fingerprint(document))throw Error(`Invalid file stage manifest: ${name}`);
  if(saved.binding_fingerprint===key){
   files.add([output]);files.seal();
   if(fingerprint(files.identity(output))!==fingerprint(saved.output))throw Error(`Corrupt file stage output: ${name}`);
   files.verify();return {path:resolve(directory,output),...saved.output,reused:true,...(saved.metadata?{metadata:saved.metadata}:{})};
  }
 }
 files.seal();const result=compute(files);files.verify();
 atomicJSON(resolve(directory,output),paths(result,files.root,'@segment/'));
 // Output is loaded once after publication to produce its immutable byte identity.
 const written=new InputFiles(directory,[output]),identity=written.identity(output);written.seal();written.verify();
 const metadata=summary?.(result),document={...binding,binding_fingerprint:key,output:identity,...(metadata?{metadata}: {})};
 atomicJSON(resolve(directory,manifest),{...document,fingerprint:fingerprint(document)});
 return {path:resolve(directory,output),...identity,reused:false,...(metadata?{metadata}: {})};
}
export function requireIdentity(files:InputFiles,name:string,expected:FileIdentity):void{
 if(!expected||fingerprint(files.identity(name))!==fingerprint({size_bytes:expected.size_bytes,sha256:expected.sha256}))throw Error(`Input artifact fingerprint mismatch: ${name}`);
}
