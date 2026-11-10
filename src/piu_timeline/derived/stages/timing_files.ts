/** Each physical/native stage loads its declared producer files once and returns a file reference. */
import {stage}from '../pipeline/file_stage.ts';
import {implementation}from '../pipeline/store.ts';
import {read as coordinates}from './coordinate_files.ts';
import {reconstruct,materialize}from './physical_timing.ts';
import {resolve as validate}from './native_timing.ts';
import type {InputFiles}from '../pipeline/input_files.ts';
import type {TimingSource}from './contracts.ts';
export function read(files:InputFiles):TimingSource{return {...coordinates(files),physical_timing:files.json('physical-timing.json')};}
export function physical(directory:string){
 return stage(directory,'physical-timing',implementation(new URL('./timing_files.ts',import.meta.url)),['coordinates.json'],'physical-timing.json',
  files=>reconstruct(coordinates(files)).physical_timing);
}
export function native(directory:string){
 return stage(directory,'native-timing',implementation(new URL('./timing_files.ts',import.meta.url)),['coordinates.json','physical-timing.json'],'native-timing.json',files=>validate(read(files)));
}
export function view(directory:string){
 return stage(directory,'physical-view',implementation(new URL('./timing_files.ts',import.meta.url)),['coordinates.json','physical-timing.json'],'physical-view.json',files=>materialize(read(files)));
}
