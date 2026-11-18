/** Source-bound image observations for play; no training on evaluated play cues. */
import {readFileSync,writeFileSync,mkdirSync,existsSync,openSync,writeSync,closeSync} from 'node:fs';
import {resolve,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseData,stringifyData} from '../json.ts';
import {hash,load} from './io.ts';
import {referenceBank} from './play_bank.ts';
import {links} from './play_links.ts';
import {SEARCH} from './play_search.ts';
import {measureWindows} from './play_pool.ts';
export const PLAY_FORMAT={schema:1,measurement:'source_bound_rgb_sequences',search:SEARCH,coverage:'all_light_candidate_windows',physical_input:'not_measured'};
const numberOf=p=>Number(basename(p).match(/segment-(\d+)/)?.[1]);
export function binding(reference,query) {
 if(resolve(reference.source)!==resolve(query.source)||['size','mtime_ns'].some(k=>String(reference.identity[k])!==String(query.source_identity[k])))throw new Error('Effect reference belongs to another source recording');
 if(!numberOf(reference.manifest.segment)||numberOf(reference.manifest.segment)!==numberOf(query.segment))throw new Error('Effect reference belongs to another segment; skin compatibility is unverified');
 if(query.selection!=='all_light_candidates')throw new Error('Play effect observations require all candidate windows, not sampled reference windows');
}
export async function analyze(referencePath:string,capturePath:string,inputPath:string,output:string) {
 const bank=referenceBank(referencePath),{capture,manifest}=load(capturePath),data=parseData(readFileSync(inputPath,'utf8'));
 binding(bank,manifest);mkdirSync(output,{recursive:true});
 const producer=Object.fromEntries(['model.ts','bank.ts','regions.ts','temporal.ts','play.ts','play_bank.ts','play_search.ts','play_measure.ts','play_pool.ts','play_worker.ts'].map(f=>[f,hash(fileURLToPath(new URL(f,import.meta.url)))]));
 const contract={format:PLAY_FORMAT,reference:hash(referencePath),capture:hash(capturePath),producer};
 const measurementPath=resolve(output,'events.json'),tracePath=resolve(output,'observations.jsonl');
 let measured;
 if(existsSync(measurementPath)&&existsSync(tracePath)) {
  const saved=parseData(readFileSync(measurementPath,'utf8'));
  if(stringifyData(saved.contract)===stringifyData(contract)&&saved.trace_sha256===hash(tracePath))measured=saved;
 }
 if(!measured) {
  const events=[],rows=[];
  for(const result of await measureWindows(capture,bank)) {
   events.push(result.event);rows.push(...result.rows);
  }
  rows.sort((a,b)=>a.playback_seconds-b.playback_seconds||a.lane-b.lane);
  const fd=openSync(tracePath,'w');
  try {for(const row of rows)writeSync(fd,stringifyData(row)+'\n');}finally {closeSync(fd);}
  measured={contract,trace_sha256:hash(tracePath),events,frame_observations:rows.length};
  writeFileSync(measurementPath,stringifyData(measured)+'\n');
 }
 const associations=links(data,measured.events);
 const counts={candidate_windows:measured.events.length,frame_observations:measured.frame_observations,
  ordered:measured.events.filter(e=>e.status==='ordered_image_candidate').length,
  appearance_only:measured.events.filter(e=>e.status==='appearance_only_phase_unresolved').length,
  reference_overlap_windows:measured.events.filter(e=>e.reference_source_overlap).length,
  unique_tap_candidates:associations.filter(e=>e.status==='unique_tap_image_candidate').length};
 const association={format:PLAY_FORMAT,producer_sha256:hash(fileURLToPath(new URL('play_links.ts',import.meta.url))),measurement_sha256:hash(measurementPath),input_sha256:hash(inputPath),associations};
 writeFileSync(resolve(output,'associations.json'),stringifyData(association)+'\n');
 const summary={format:PLAY_FORMAT,reference:resolve(referencePath),reference_sha256:hash(referencePath),counts,
  report:'effect-images/report.html',observations:'effect-images/observations.jsonl',events:'effect-images/events.json',associations:'effect-images/associations.json',
  scope:'Light-cue image observations; unobserved frames are not measured. Appearance and image-order evidence do not establish physical input times.'};
 writeFileSync(resolve(output,'summary.json'),stringifyData(summary)+'\n');
 const byEvent=new Map<string,ReturnType<typeof links>[number]>(associations.map(a=>[a.event,a]));
 const escape=v=>String(v??'—').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
 let html='<!doctype html>'+
  '<meta charset="utf-8">'+
  '<title>Play effect image evidence</title>'+
  '<style>body{font:16px system-ui;max-width:1200px;margin:30px auto;background:#171b20;color:#eee}a{color:#9cf}td,th{padding:7px;border:1px solid #566}table{border-collapse:collapse}</style>'+
  '<h1>Play effect image evidence</h1>'+
  '<p>'+escape(summary.scope)+'</p>'+
  '<p>'+
  '<a href="../report.html">Play report</a> · <a href="events.json">Sequence observations</a> · <a href="observations.jsonl">Per-frame positions and stage alternatives</a> · <a href="associations.json">Note and popup candidates</a>'+
  '</p>'+
  '<p>'+escape(JSON.stringify(counts))+'</p>'+
  '<p>Search uses sampled RGB proposals followed by full-resolution validation; ordered statuses remain candidates within that search. Positions use the receptor prior and local RGB translation. Reference stages are marker-relative, not calibrated effect ages. RGB outlier regions are possible contamination, not verified opacity. No target, physical input, grade or existing popup assignment is changed.</p>'+
  '<table>'+
  '<tr>'+
  '<th>Window</th>'+
  '<th>Lane</th>'+
  '<th>Image status</th>'+
  '<th>Observed interval</th>'+
  '<th>Note relation</th>'+
  '<th>Candidate notes</th>'+
  '</tr>';
 for(const e of measured.events) {
  const a=byEvent.get(e.id);
  html+=`<tr><td>${escape(e.id)}</td><td>${e.lane+1}</td><td>${escape(e.status)}</td><td>${e.observation_range.map(t=>t.toFixed(3)).join(' – ')}</td><td>${escape(a.status)}</td><td>${escape(a.candidates.map(c=>c.note).join(', '))}</td></tr>`;
 }
 writeFileSync(resolve(output,'report.html'),html+'</table>');return summary;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
 if(process.argv.length!==6)throw new Error('Usage: play.ts REFERENCE_JSON CAPTURE_JSON PLAY_INPUT_JSON OUTPUT_DIR');
 console.log(stringifyData(await analyze(...process.argv.slice(2) as [string,string,string,string])));
}
