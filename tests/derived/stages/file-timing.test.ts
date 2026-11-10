/** Persisted timing stages must produce the generator's chart, independent of previous views. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,rmSync,writeFileSync,statSync}from 'node:fs';
import {join}from 'node:path';
import {tmpdir}from 'node:os';
import {createHash}from 'node:crypto';
import {save}from '../../../src/piu_timeline/derived/stages/coordinate_files.ts';
import {physical,native}from '../../../src/piu_timeline/derived/stages/timing_files.ts';
import {prepare,calculate,view}from '../../../src/piu_timeline/derived/beats/files.ts';
import {nativeScene}from '../fixtures.ts';

test('saved coordinates recover a chord and following row; stale dependencies and damaged output fail',()=>{
 const root=mkdtempSync(join(tmpdir(),'piu-file-timing-'));
 try{
  const expected=[.875,.875,1.125],data=nativeScene(expected.map((t,i)=>[t,i]),40,60,5,{end:1.3});
  data.frame_timeline=data.scroll_motion.samples.map(({time,source_pts})=>({time,source_pts}));
  data.notes.forEach(n=>Object.assign(n,{target_seconds:999,status:'excluded'}));
  writeFileSync(join(root,'coordinate-input.json'),JSON.stringify({schema:1,identity:{media:{mtime_ns:'1780000000000000001'}},data}));
  save(root);physical(root);native(root);
  const timing=':Format=1\n:Mode=Single\n:BPM=120\n:Beat=4\n:Split=4\n'+'.....\n'.repeat(32),path=join(root,'official.ucs');
  writeFileSync(path,timing);
  const ref={status:'available',timing:path,sha256:createHash('sha256').update(timing).digest('hex'),song_start_seconds:0,alignment_uncertainty_seconds:0};
  writeFileSync(join(root,'beat-reference.json'),JSON.stringify({schema:1,reference:ref}));
  prepare(root);calculate(root);const output=view(root),result=JSON.parse(readFileSync(output.path,'utf8'));
  assert.equal(result.beat_timing.status,'restored');assert.equal(result.notes.length,3);
  result.notes.forEach((n,i)=>{assert.equal(n.status,'estimated');assert.ok(Math.abs(n.target_seconds-expected[i])<1e-8);assert.deepEqual(n.points,data.notes[i].points);});
  assert.deepEqual(result.frame_timeline,data.frame_timeline);
  const stamp=statSync(output.path,{bigint:true}).mtimeNs;
  physical(root);native(root);prepare(root);calculate(root);assert.equal(view(root).reused,true);
  assert.equal(statSync(output.path,{bigint:true}).mtimeNs,stamp);
  writeFileSync(path,timing.replace('BPM=120','BPM=121'));
  assert.throws(()=>calculate(root),/fingerprint mismatch/);
  assert.throws(()=>prepare(root),/fingerprint mismatch/);
  writeFileSync(path,timing);writeFileSync(join(root,'beat-result.json'),'{}');
  assert.throws(()=>calculate(root),/Corrupt file stage output/);
  assert.throws(()=>view(root),/Expected beats/);
 }finally{rmSync(root,{recursive:true,force:true});}
});
