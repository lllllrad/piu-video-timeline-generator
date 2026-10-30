/** Indexed result patches cannot rewrite observations or another stage's fields. */
import {equal} from '../math.ts';
import type {RecordData} from '../types.ts';
export interface NotePatch {note:number;values:Readonly<Record<string,unknown>>;removed:readonly string[]}
export function changes(before:RecordData[],after:RecordData[],allowed:readonly string[]):NotePatch[]{
 if(before.length!==after.length)throw new Error('Stage changed observation identities');
 return after.flatMap((n,note)=>{
  const previous=before[note],keys=new Set([...Object.keys(previous),...Object.keys(n)]);
  for(const k of keys)if(!allowed.includes(k)&&(!equal(previous[k],n[k])||Object.hasOwn(previous,k)!==Object.hasOwn(n,k)))
   throw new Error(`Stage rewrote unowned note field: ${k}`);
  const changed=allowed.filter(k=>!equal(previous[k],n[k])||Object.hasOwn(previous,k)!==Object.hasOwn(n,k));
  return changed.length?[{note,values:Object.fromEntries(changed.filter(k=>Object.hasOwn(n,k)).map(k=>[k,n[k]])),
   removed:changed.filter(k=>!Object.hasOwn(n,k))}]:[];
 });
}
export function apply(notes:RecordData[],patches:readonly NotePatch[],allowed:readonly string[]):RecordData[]{
 const indexed=new Map(patches.map(p=>[p.note,p]));
 if(indexed.size!==patches.length||patches.some(p=>!Number.isInteger(p.note)||p.note<0||p.note>=notes.length||
  [...Object.keys(p.values),...p.removed].some(k=>!allowed.includes(k))))throw new Error('Stage contains foreign note fields or identities');
 return notes.map((n,i)=>{
  const p=indexed.get(i);if(!p)return {...n};
  const next={...n,...structuredClone(p.values)};p.removed.forEach(k=>delete next[k]);return next;
 });
}
