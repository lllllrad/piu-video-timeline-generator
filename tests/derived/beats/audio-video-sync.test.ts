import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {reconstruct} from '../../../src/piu_timeline/derived/beats/reconstruct.ts';
import {transcriptionAlignment} from '../../../src/piu_timeline/derived/charts/phase.ts';
import {parse, text} from '../../../src/piu_timeline/derived/charts/ucs.ts';
import {apply, recovery} from './fixtures.ts';

const template=parse(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'.repeat(32));
const alignment={method:'reference_audio_translation',song_start_seconds:10,uncertainty_seconds:.01,rate:1};
function scene(offset:number,method='reference_audio_translation'){
 const reference={status:'available',song_start_seconds:10,alignment_uncertainty_seconds:.01,alignment_method:method,
  sha256:createHash('sha256').update(text(template)).digest('hex')};
 const data={notes:Array.from({length:6},(_,i)=>({lane:i%5,status:'estimated',target_seconds:11+i*.5+offset,
  prediction_uncertainty_seconds:.001,points:[[10,200],[10.02,190]]}))};
 return {schema:1 as const,data,reference,timing_text:text(template)};
}

for(const offset of[-.06,.06])test(`video phase differs from audio by ${offset}s while official timing stays fixed`,()=>{
 const input=scene(offset),before=structuredClone(input),result=reconstruct(input),beat=result.beat_timing;
 assert.equal(beat.status,'restored');assert.ok(Math.abs(beat.song_phase_correction_seconds-offset)<.001);
 assert.equal(beat.song_phase_search.audio_uncertainty_seconds,.01);
 assert.ok(beat.song_phase_search.audio_video_sync_search_seconds>.099);
 assert.ok(beat.groups.every(g=>g.split===1));
 const [effective,proof]=transcriptionAlignment(template,result,alignment);
 assert.ok(Math.abs(effective.song_start_seconds-(10+offset))<.001);
 assert.ok(effective.uncertainty_seconds<.002);
 assert.equal(proof.audio_song_start_seconds,10);assert.equal(proof.audio_uncertainty_seconds,.01);
 result.notes.forEach((n,i)=>{
  assert.ok(Math.abs(n.target_seconds-effective.song_start_seconds-(1+i*.5))<1e-9);
  assert.ok(Math.abs(n.target_seconds-input.data.notes[i].target_seconds)<=.001+1e-9);
 });
 assert.deepEqual(input,before);assert.equal(text(template),input.timing_text);
});

test('reviewed video origins do not receive an audio/video search allowance',()=>{
 const r=reconstruct(scene(.06,'explicit_song_start'));
 assert.equal(r.beat_timing.song_phase_search.audio_video_sync_search_seconds,0);
 assert.ok(r.beat_timing.phase_trials.every(p=>Math.abs(p.phase_seconds)<=.01));
});

test('the sync search radius does not widen recovered native target ranges',()=>{
 const r=apply(recovery(),0,{alignment_method:'reference_audio_translation',alignment_uncertainty_seconds:.01});
 const baseline=apply(recovery(),0,{alignment_method:'explicit_song_start',alignment_uncertainty_seconds:.01}).notes[4],note=r.notes[4];
 assert.equal(note.status,'estimated');assert.equal(note.fit_method,'native_beat_coordinate_interpolation');
 assert.equal(note.prediction_uncertainty_seconds,baseline.prediction_uncertainty_seconds);
 assert.deepEqual(note.video_target_range,baseline.video_target_range);
});

test('audio alone or a mismatched visual phase cannot establish a UCS origin',()=>{
 assert.throws(()=>transcriptionAlignment(template,{},alignment),/supported visual song phase/);
 const r=reconstruct(scene(.06));r.beat_timing.contract.reference.sha256='changed timing';
 assert.throws(()=>transcriptionAlignment(template,r,alignment),/supported visual song phase/);
});

test('incompatible visual timing retains explicit reconstruction warnings',()=>{
 const input=scene(.06);input.data.notes.forEach(n=>n.prediction_uncertainty_seconds=0);
 input.data.notes[2].target_seconds+=.000123456;
 const r=reconstruct(input);
 assert.equal(r.beat_timing.status,'failed');
 assert.ok(r.beat_timing.warnings.some(w=>w.reason==='beat_timing_reconstruction_failed'));
});

test('an uncertain audio/video origin cannot assign a tempo-boundary note to the wrong BPM',()=>{
 const input=scene(-.06);
 input.timing_text=text(template).replace('.....\n'.repeat(32),'.....\n'.repeat(8)+':BPM=180\n'+'.....\n'.repeat(24));
 // The second section begins at song time 1s. This note is 60ms early only
 // in the audio clock; it belongs to the new tempo in the visual clock.
 const r=reconstruct(input);
 assert.ok(r.beat_timing.warnings.some(w=>w.note===0&&w.failure_detail==='audio_video_sync_crosses_tempo_boundary'));
 assert.equal(r.notes[0].target_seconds,null);
});
