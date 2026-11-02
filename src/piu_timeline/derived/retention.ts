/** Bounded local analysis history. Call only after successful publication, under its writer lock. */
import {lstatSync, readdirSync, readFileSync, realpathSync, rmSync, statSync} from 'node:fs';
import {basename, dirname, join, relative, resolve, sep} from 'node:path';

export interface RetentionResult {removed:string[];kept:string[];reason?:string}

function directory(path:string):boolean {
  try {const stat=lstatSync(path);return stat.isDirectory()&&!stat.isSymbolicLink();}
  catch(error) {if(error.code==='ENOENT')return false;throw error;}
}

function file(path:string):boolean {
  try {return lstatSync(path).isFile()&&statSync(path).size>0;}
  catch(error) {if(error.code==='ENOENT')return false;throw error;}
}

function inside(path:string,root:string):boolean {
  const suffix=relative(root,path);
  return suffix===''||suffix!=='..'&&!suffix.startsWith('..'+sep)&&!suffix.startsWith(sep);
}

function timestamp(path:string):number {
  try {return statSync(join(path,'analysis.json')).mtimeMs;}
  catch(error) {if(error.code==='ENOENT')return statSync(path).mtimeMs;throw error;}
}

function manifest(path:string):boolean {
  try {
    const document=JSON.parse(readFileSync(join(path,'analysis.json'),'utf8'));
    return document!==null&&typeof document==='object'&&!Array.isArray(document);
  } catch(error) {if(error instanceof SyntaxError||error.code==='ENOENT')return false;throw error;}
}

export function prune(finalPath:string,newPrevious:string|null=null,protectedPaths:string[]=[]):RetentionResult {
  const final=resolve(finalPath),name=basename(final),parent=dirname(final);
  if(!/^(?:analysis|segment-\d{3})$/.test(name))throw new Error('Retention requires a canonical analysis directory');
  const play=name.startsWith('segment-');
  const required=play?['analysis.json','frames.jsonl','frames.base.jsonl','report.html']:['analysis.json'];
  if(!directory(final)||!required.every(part=>file(join(final,part)))||!manifest(final)) {
    return {removed:[],kept:[],reason:'Canonical result or immutable native baseline is incomplete'};
  }
  const pattern=new RegExp(`^${name}\\.(previous|build)-[a-f0-9]+$`);
  const candidates=readdirSync(parent).filter(entry=>pattern.test(entry))
    .map(entry=>join(parent,entry)).filter(directory);
  const previous=candidates.filter(path=>basename(path).startsWith(name+'.previous-'))
    .sort((a,b)=>timestamp(b)-timestamp(a)||a.localeCompare(b));
  const recoverable=(path:string)=>file(join(path,'analysis.json'))&&(!play||file(join(path,'frames.jsonl')))&&manifest(path);
  const explicit=newPrevious===null?null:resolve(newPrevious);
  if(explicit!==null&&!previous.includes(explicit))throw new Error('Published rollback must be a sibling snapshot');
  const retained=explicit&&recoverable(explicit)?explicit:previous.find(recoverable)??previous[0];
  const protectedLocations=protectedPaths.flatMap(path=>{
    const absolute=resolve(path);
    try {return [absolute,realpathSync(absolute)];}
    catch(error) {if(error.code==='ENOENT')return [absolute];throw error;}
  });
  const kept=candidates.filter(path=>path===retained||protectedLocations.some(source=>inside(source,path)));
  const removed=candidates.filter(path=>!kept.includes(path));
  for(const path of removed)rmSync(path,{recursive:true});
  return {removed,kept};
}
