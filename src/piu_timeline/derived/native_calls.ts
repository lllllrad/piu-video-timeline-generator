/** Explicit results for native Python callers; no hidden mutation return channel. */
import {associate}from './association.ts';
import {dirname,basename}from 'node:path';
import {InputFiles}from './pipeline/input_files.ts';
import {processing}from './pipeline/inputs.ts';
import {judgmentInput,judgments}from './stages/associations.ts';
import {spacingFailures}from './beats/spacing.ts';
import type {RecordData,Note,CoordinateSupport}from './types.ts';
export function counterAlignment(notes:RecordData[],events:RecordData[],window:number,delay:number,constraints:Record<string,number[]>|null){
 const working=structuredClone(events),matches=associate(notes,working,window,delay,constraints);
 return {matches,events:working.map(e=>Object.fromEntries(['status','reason'].filter(k=>Object.hasOwn(e,k)).map(k=>[k,e[k]])))};
}
export function spacingCheck(notes:Note[],spacing:number,motion:RecordData|null,support:CoordinateSupport|null,
 baseline:number[]|null,changed:number[]|null,includeDiagnostics:boolean){
 const diagnostics:RecordData[]=[];
 const failures=spacingFailures(notes,spacing,motion,support,includeDiagnostics?diagnostics:null,baseline,changed);
 return {failures,diagnostics};
}

export function judgmentAssociation(data:RecordData,events:RecordData[],observations:RecordData[]){
 return judgments(judgmentInput(data,events,observations));
}

export function processingFile(path:string){
 const files=new InputFiles(dirname(path),[basename(path)]);files.seal();
 const result=processing(files.json(basename(path)));files.verify();return result;
}
