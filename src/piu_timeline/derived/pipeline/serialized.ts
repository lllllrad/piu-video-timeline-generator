/** File-bound stages check upstream bytes before loading or rebuilding an input. */
import {createHash}from 'node:crypto';
import {readFileSync,existsSync,statSync,openSync,readSync,closeSync}from 'node:fs';
import {resolve,isAbsolute}from 'node:path';
import {atomicJSON,fingerprint}from './store.ts';
import {parseData}from '../json.ts';
import type {RecordData}from '../types.ts';

const identities=new Map<string,{size_bytes:number;sha256:string}>();
export function identity(path:string,directory?:string){
 const stamp=statSync(path,{bigint:true}),key=[resolve(path),directory??'',stamp.dev,stamp.ino,stamp.size,stamp.mtimeNs,stamp.ctimeNs].join('\0');
 if(identities.has(key))return {...identities.get(key)};
 const hash=createHash('sha256'),buffer=Buffer.allocUnsafe(1024*1024),fd=openSync(path,'r'),before=stamp,
  prefix=directory?Buffer.from(JSON.stringify(resolve(directory)+'/').slice(0,-1)):null,replacement=Buffer.from('"@segment/');
 let pending=Buffer.alloc(0),size=0;
 const consume=(bytes:Buffer)=>{hash.update(bytes);size+=bytes.length;};
 const flush=(final:boolean)=>{
  if(!prefix){consume(pending);pending=Buffer.alloc(0);return;}
  let cut=final?pending.length:Math.max(0,pending.length-prefix.length+1),start=0,match:number;
  while((match=pending.indexOf(prefix,start))>=0&&match<cut){
   consume(pending.subarray(start,match));consume(replacement);start=match+prefix.length;cut=Math.max(cut,start);
  }
  consume(pending.subarray(start,cut));pending=Buffer.from(pending.subarray(cut));
 };
 try{let count:number;while((count=readSync(fd,buffer,0,buffer.length,null))){pending=Buffer.concat([pending,buffer.subarray(0,count)]);flush(false);}flush(true);}
 finally{closeSync(fd);}
 const after=statSync(path,{bigint:true});
 if(before.dev!==after.dev||before.ino!==after.ino||before.size!==after.size||before.mtimeNs!==after.mtimeNs||before.ctimeNs!==after.ctimeNs)throw Error('Serialized artifact changed while reading');
 const result={size_bytes:size,sha256:hash.digest('hex')};
 if(identities.size>=128)identities.clear();identities.set(key,result);return {...result};
}
export function definition(directory:string,stage:string,producer:string,parameters:RecordData,inputs:string[]){
 if(!/^[a-z][a-z-]*$/.test(stage))throw Error('Invalid serialized stage');
 const sources=Object.fromEntries(inputs.map(name=>{
  if(isAbsolute(name)||name.split(/[\\/]/).includes('..'))throw Error('Invalid upstream artifact path');
  return [name,identity(resolve(directory,name),directory)];
 }));
 return {schema:1,stage,producer,parameters,inputs:sources};
}
export function lookup(directory:string,binding:RecordData):RecordData|null{
 const path=resolve(directory,`${binding.stage}.stage.json`);
 if(!existsSync(path))return null;
 const saved=parseData(readFileSync(path,'utf8'));
 if(saved.schema!==1||saved.stage!==binding.stage)throw Error('Invalid serialized stage manifest');
 if(saved.binding_fingerprint!==fingerprint(binding))return null;
 for(const name of ['input','output']){
  const file=resolve(directory,`${binding.stage}-${name}.json`),expected=saved[name];
  if(!expected||fingerprint(identity(file,directory))!==fingerprint(expected))throw Error(`Corrupt serialized stage ${name}`);
 }
 return {path:resolve(directory,`${binding.stage}-output.json`),...saved.output};
}
export function run(directory:string,binding:RecordData,compute:(input:RecordData)=>RecordData){
 const old=lookup(directory,binding);if(old)return old;
 const inputPath=resolve(directory,`${binding.stage}-input.json`),input=identity(inputPath,directory),
  outputPath=resolve(directory,`${binding.stage}-output.json`),result=compute(parseData(readFileSync(inputPath,'utf8')));
 if(fingerprint(definition(directory,binding.stage,binding.producer,binding.parameters,Object.keys(binding.inputs)))!==fingerprint(binding)||
  fingerprint(identity(inputPath,directory))!==fingerprint(input))throw Error('Serialized stage inputs changed during calculation');
 atomicJSON(outputPath,result);
 const output=identity(outputPath,directory);
 atomicJSON(resolve(directory,`${binding.stage}.stage.json`),{...binding,binding_fingerprint:fingerprint(binding),input,output});
 return {path:outputPath,...output};
}
