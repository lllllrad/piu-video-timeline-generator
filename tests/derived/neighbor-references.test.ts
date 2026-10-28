import test from 'node:test';
import assert from 'node:assert/strict';
import {neighborReferenceScene,template} from './fixtures.ts';
import {fitGroups} from '../../src/piu_timeline/derived/beats/phase.ts';
import {reconstruct} from '../../src/piu_timeline/derived/beats/stage.ts';
import {text} from '../../src/piu_timeline/derived/charts/ucs.ts';

for(const spacing of [20,40,80])for(const fps of [30,60,120])test(`obsolete neighbor rows cannot erase independently supported groups: spacing=${spacing}, fps=${fps}`,()=>{
  const s=neighborReferenceScene(spacing,fps),before=structuredClone(s),fits=fitGroups(s.groups,0);
  assert.equal(fits[0].status,'partial');assert.equal(fits[0].targets[5],null,'the unsupported coarse row is not reinstated');
  assert.equal(fits[1].status,'restored','the neighboring group must be recomputed rather than discarded');
  assert.deepEqual(fits[1].targets,s.groups[1].notes.map(i=>s.events[i][0]));
  const history=fits[1].neighbor_reference_resolution;assert.equal(history.length,1);
  assert.ok(history.every(r=>r.note===5&&r.reference_target_seconds===1.875&&r.final_target_seconds===null));
  const final=new Map(s.groups.flatMap((g,i)=>g.notes.map((n,j)=>[n,fits[i].targets[j]])));
  for(const f of fits)for(const proof of f.native_coordinate_constraints??[])for(const r of proof.model.references)
    assert.equal(r.target_seconds,final.get(r.note),'every retained proof must use the final reference row');
  assert.deepEqual(s,before);
});

test('an external-reference failure cannot leave downstream proofs using the failed group',()=>{
  const s=neighborReferenceScene(),groups=structuredClone(s.groups),receptor=s.data.layout.receptor_y*s.data.analysis_height;
  Object.assign(groups[1].native_coordinates[0],{references:[{note:99,lane:4,target_seconds:1.5,offset:receptor+240*1.5}]});
  const fits=fitGroups(groups,0);assert.equal(fits[1].status,'failed');
  const final=new Map(groups.flatMap((g,i)=>g.notes.map((n,j)=>[n,fits[i].targets?.[j]??null])));
  for(const f of fits)for(const p of f.native_coordinate_constraints??[])for(const r of p.model.references)
    assert.equal(r.target_seconds,final.get(r.note));
});

test('full native-to-beat reconstruction retains independent rows and warns about the unresolved crossing',()=>{
  const s=neighborReferenceScene(),before=structuredClone(s.data);
  const result=reconstruct({schema:1,data:s.data,reference:{status:'available',song_start_seconds:0,alignment_uncertainty_seconds:0},timing_text:text(template())});
  for(const i of s.groups[1].notes){assert.equal(result.notes[i].status,'estimated');assert.equal(result.notes[i].target_seconds,s.events[i][0]);}
  assert.equal(result.notes[5].status,'excluded');assert.ok(result.beat_timing.warnings.some(w=>w.note===5));
  assert.ok(result.timing_reconstruction.warnings.some(w=>w.note===5&&w.reason==='shared_subframe_clock_unresolved'));
  assert.equal(result.beat_timing.status,'failed');assert.deepEqual(s.data,before);
  assert.deepEqual(result.notes.map(n=>n.points),s.data.notes.map(n=>n.points));
});

test('an invalid external reference remains a failure when no provisional assignment can be withdrawn',()=>{
  const s=neighborReferenceScene(),g=structuredClone(s.groups[1]);
  const left=s.groups[0].native_coordinates[0].heads;
  Object.assign(g.native_coordinates[0],{references:Object.values(left).slice(0,5).map(h=>({...h,note:h.native_note,target_seconds:s.events[h.native_note][0]}))});
  const [f]=fitGroups([g],0);
  assert.equal(f.status,'failed');assert.equal(f.reason,'unstable_neighbor_reference_rows');
  assert.ok(f.neighbor_reference_resolution.every(r=>r.final_target_seconds===null));
});
