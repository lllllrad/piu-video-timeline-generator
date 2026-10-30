import test from 'node:test';import assert from 'node:assert/strict';
import {spacingFailures} from '../../../src/piu_timeline/derived/beats/spacing.ts';
import {prepare} from '../../../src/piu_timeline/derived/beats/coordinates.ts';
import {fitPhase} from '../../../src/piu_timeline/derived/beats/phase.ts';
import {spacingSupportedNotes} from '../../../src/piu_timeline/derived/beats/validation.ts';
import {coordinates,spatial,stagger,apply,near} from './fixtures.ts';

function clockPair(){
 const times=Array.from({length:8},(_,i)=>.4+i/60),clock={origin:0,velocity:480,intercept:0,residual:3,window:[0,.5]};
 return {notes:[0,1].map(i=>({lane:i,status:'estimated',target_seconds:1+.1*i,points:times.map(t=>[t,200+50*i-480*(t-.4)]),motion_clock:clock,motion_target_phase:480+50*i})),
  motion:{samples:times.map(time=>({time,chunk:0})),coordinate_registration:{chunks:[{chunk:0,status:'fitted',head_offsets:[0,1].map(i=>({note:i,offset_pixels:200+50*i}))}]}}};
}
test('short beat corrections propagate measured clock slope error without widening coordinate precision',()=>{
 const {notes,motion}=clockPair(),before=structuredClone({notes,motion}),checks=[];
 assert.deepEqual(spacingFailures(notes as any,40,motion,null,checks),[]);
 assert.ok(near(checks[0].clock_conversion.velocity_error_pixels_per_second,18));assert.ok(near(checks[0].clock_conversion.position_error_pixels,1.8));
 assert.deepEqual({notes,motion},before);
});
for(const kind of['exact_clock','wrong_row'])test(`a clock error cannot excuse a refuted row: ${kind}`,()=>{
 const {notes,motion}=clockPair();if(kind==='exact_clock')notes[0].motion_clock.residual=0;else notes[1].target_seconds+=.04;
 const failed=spacingFailures(notes as any,40,motion);assert.deepEqual([...new Set(failed.map(w=>w.note))],[0,1]);assert.equal(failed[0].tolerance_pixels,1);
});
test('independent native models retain the original pixel gate despite large clock residuals',()=>{
 const d=coordinates();d.notes.forEach(n=>n.motion_clock={origin:0,velocity:240,intercept:0,residual:100,window:[0,1]});
 const support=prepare(d,40);d.notes[4].target_seconds+=.06;const failed=spacingFailures(d.notes,40,d.scroll_motion,support),pair=failed.find(w=>w.peer_notes.join()==='4,5');
 assert.equal(pair.tolerance_pixels,1);assert.ok(!Object.hasOwn(pair,'clock_conversion'));assert.deepEqual([...new Set(failed.map(w=>w.note))],[4]);
});
for(const registered of[false,true])test(`an eight millisecond stagger survives, but its collapsed row fails: registered=${registered}`,()=>{
 const d=stagger(),before=structuredClone(d);assert.deepEqual(spacingFailures(d.notes,40,registered?d.motion:null),[]);assert.deepEqual(d,before);
 d.notes[1].target_seconds=1;const failed=spacingFailures(d.notes,40,registered?d.motion:null);
 assert.deepEqual(failed.map(w=>w.note),[0,1]);assert.ok(failed.every(w=>w.reason==='shared_spacing_reconstruction_conflict'));
 assert.ok(near(failed[0].observed_gap_pixels,4));assert.ok(near(failed[0].reconstructed_gap_pixels,0));
});
test('raster differences alone do not prove separation, while missing shared geometry stays unresolved',()=>{
 for(const gap of[0,1,2]){const d=stagger(gap);d.notes[1].target_seconds=1;assert.deepEqual(spacingFailures(d.notes,40,d.motion),[]);}
 const d=stagger();d.motion.coordinate_registration.chunks=[];
 assert.deepEqual([...new Set(spacingFailures(d.notes,40,d.motion).map(w=>w.reason))],['shared_spacing_model_unavailable']);
});
test('full reconstruction explicitly rejects unique clock rows that collapse an observed stagger',()=>{
 const d=stagger();d.notes.forEach(n=>n.prediction_uncertainty_seconds=.01);
 const source={notes:d.notes,scroll_motion:d.motion,analysis_width:400,analysis_height:400,layout:{receptor_y:.1,lanes:Array.from({length:5},(_,i)=>({x:.2+.1*i}))}},before=structuredClone(source),r=apply(source);
 assert.deepEqual(source,before);assert.ok(r.notes.every(n=>n.status==='excluded'));
 assert.deepEqual([...new Set(r.beat_timing.warnings.map(w=>w.reason))],['beat_timing_reconstruction_failed']);
 assert.equal(r.beat_timing.phase_trials[0].consistent_targets,0);assert.ok(r.beat_timing.warnings.every(w=>w.failure_detail==='ambiguous_or_unsupported_song_phase'));
});
function biased(){const d=coordinates();for(const [i,direction]of[[4,1],[5,-1]])d.notes[i].points=d.notes[i].points.map(([t,y],j)=>[t,y+direction*(j<6?.6:-.9)]);
 d.notes.push({lane:3,status:'estimated',target_seconds:1.5625,points:d.notes[4].points.slice(6).map(([t])=>[t,40+240*(1.5625-t)])});return d;}
test('full registered offsets keep their pixel limit even when raw adjacency has a biased subset',()=>{
 const d=biased(),before=structuredClone(d),checks=[];assert.deepEqual(spacingFailures(d.notes,40,d.scroll_motion,prepare(d,40),checks),[]);
 const pair=checks.find(c=>c.peer_notes.join()==='4,5');assert.ok(near(pair.observed_gap_pixels,28.8));assert.ok(near(pair.comparison_gap_pixels,30));
 assert.equal(pair.comparison_basis,'independent_registered_offsets');assert.deepEqual(d,before);
});
for(const kind of['wrong_row','invalid_native'])test(`wrong rows and unverified offsets cannot pass registered spacing: ${kind}`,()=>{
 const d=biased();if(kind==='wrong_row')d.notes[4].target_seconds+=.06;else d.notes[4].points[0][1]+=3;
 const p=spacingFailures(d.notes,40,d.scroll_motion,prepare(d,40)).find(w=>w.peer_notes.join()==='4,5');assert.equal(p.tolerance_pixels,1);
 if(kind==='wrong_row')assert.ok(Math.abs(p.reconstructed_gap_pixels-p.comparison_gap_pixels)>1);else assert.ok(!Object.hasOwn(p,'comparison_basis'));
});
test('observed native spacing narrows a common beat phase and preserves its inputs',()=>{
 const d=spatial(),before=structuredClone(d),validator=fits=>spacingSupportedNotes(d.notes,d.groups,fits,40,d.motion);
 const timing=fitPhase(d.groups,.01),r=fitPhase(d.groups,.01,validator);
 assert.equal(r.status,'restored');assert.deepEqual(r.consistent_notes,[0,1]);assert.ok(r.phase_range[0]>timing.phase_range[0]);
 assert.deepEqual(validator(r.fits),[0,1]);assert.ok(r.phase_trials.some(t=>t.consistent_targets<t.restored_targets));assert.deepEqual(d,before);
});
test('neither a common phase nor equal scores can hide spatially different supported identities',()=>{
 const d=spatial();d.motion.coordinate_registration.chunks[0].head_offsets[1].offset_pixels+=6;
 const r=fitPhase(d.groups,.01,fits=>spacingSupportedNotes(d.notes,d.groups,fits,40,d.motion));assert.equal(r.status,'failed');
 assert.ok(r.fits.every(f=>f.status==='failed'));assert.ok(r.phase_trials.every(t=>t.consistent_targets===0));
 const ambiguous=fitPhase([{targets:[1],errors:[.02],bpm:120,origin:0}],.01,fits=>fits[0].targets[0]<1?[0]:[1]);
 assert.equal(ambiguous.status,'failed');assert.equal(ambiguous.reason,'ambiguous_or_unsupported_song_phase');
});
