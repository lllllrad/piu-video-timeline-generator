/** Persisted association producers; request construction and calculation stay in TypeScript. */
import {stage}from '../pipeline/file_stage.ts';
import {implementation}from '../pipeline/store.ts';
import {counters,judgments,judgmentInput}from './associations.ts';
export function counter(directory:string){
 return stage(directory,'counter-associations',implementation(new URL('./association_files.ts',import.meta.url)),
  ['counter-input.json'],'counter-associations.json',files=>counters(files.json('counter-input.json'),files.root));
}
export function judgment(directory:string){
 return stage(directory,'judgment-associations',implementation(new URL('./association_files.ts',import.meta.url)),
  ['judgment-source.json'],'judgment-associations.json',files=>{
   const source=files.json('judgment-source.json');
   if(source.schema!==1)throw Error('Invalid judgment source file');
   return judgments(judgmentInput(source.data,source.events,source.observations),files.root);
  });
}
