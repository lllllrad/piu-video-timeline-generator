/** One invocation owns one complete input snapshot; calculations never reopen files. */
import {readFileSync,statSync}from 'node:fs';
import {resolve}from 'node:path';
import {createHash}from 'node:crypto';
import {parseData}from '../json.ts';
export interface FileIdentity {size_bytes:number;sha256:string}
export type Reader=(path:string)=>Buffer;
const stamp=(path:string)=>{const s=statSync(path,{bigint:true});return [s.dev,s.ino,s.size,s.mtimeNs,s.ctimeNs].join(':');};
export function paths(value:any,before:string,after:string):any{
 if(typeof value==='string')return value.startsWith(before)?after+value.slice(before.length):value;
 if(Array.isArray(value))return value.map(v=>paths(v,before,after));
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,paths(v,before,after)]));
 return value;
}
export function contentIdentity(bytes:Buffer,root:string):FileIdentity{
 const prefix=Buffer.from(JSON.stringify(root).slice(0,-1)),replacement=Buffer.from('"@segment/'),hash=createHash('sha256');
 let start=0,match:number,size=0;
 while((match=bytes.indexOf(prefix,start))>=0){hash.update(bytes.subarray(start,match));hash.update(replacement);size+=match-start+replacement.length;start=match+prefix.length;}
 hash.update(bytes.subarray(start));size+=bytes.length-start;
 return {size_bytes:size,sha256:hash.digest('hex')};
}
interface Loaded {bytes:Buffer;stamp:string;identity:FileIdentity;text?:string;value?:any;parsed?:boolean}
export class InputFiles {
 readonly root:string;
 private readonly loaded=new Map<string,Loaded>();
 private sealed=false;
 private readonly reader:Reader;
 constructor(directory:string,names:readonly string[],reader:Reader=readFileSync){
  this.reader=reader;this.root=resolve(directory)+'/';this.add(names);
 }
 private path(name:string){return resolve(this.root,name);}
 add(names:readonly string[]):void{
  if(this.sealed)throw Error('Stage input loading is closed');
  for(const name of names){
   const path=this.path(name);if(this.loaded.has(path))continue;
   const before=stamp(path),bytes=this.reader(path),after=stamp(path);
   if(before!==after)throw Error('Stage input changed while reading');
   this.loaded.set(path,{bytes,stamp:after,identity:contentIdentity(bytes,this.root)});
  }
 }
 seal():void{this.sealed=true;}
 private get(name:string):Loaded{
  const value=this.loaded.get(this.path(name));
  if(!value)throw Error(`Input was not loaded at stage start: ${name}`);
  return value;
 }
 text(name:string):string{const value=this.get(name);return value.text??=(value.bytes.toString('utf8'));}
 json<T=any>(name:string):T{
  const value=this.get(name);
  if(!value.parsed){value.value=paths(parseData(this.text(name)),'@segment/',this.root);value.parsed=true;}
  return value.value;
 }
 identity(name:string):FileIdentity{return {...this.get(name).identity};}
 verify():void{for(const [path,value]of this.loaded)if(stamp(path)!==value.stamp)throw Error('Stage input changed during calculation');}
 identities(names:readonly string[]):Record<string,FileIdentity>{return Object.fromEntries(names.map(n=>[n,this.identity(n)]));}
}
