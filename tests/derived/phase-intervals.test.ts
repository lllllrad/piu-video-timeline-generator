import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene} from './fixtures.ts';
import {fitPhase} from '../../src/piu_timeline/derived/beats/phase.ts';
import {spacingFailures} from '../../src/piu_timeline/derived/beats/spacing.ts';

function fixture(spacing=40,fps=60,intervals=[[.0004,.0005]]){
 const phase=intervals.reduce((n,[lo])=>Math.max(n,lo),-Infinity)+.00005;
 const events: [number,number][]=intervals.flatMap((_,g)=>Array.from({length:4},(_,i)=>[1+g*2+i*.25+phase,i%5]));
 const d=nativeScene(events,spacing,fps,5,{end:intervals.length*2+.5});
 const groups=intervals.map(([lo,hi],g)=>({notes:Array.from({length:4},(_,i)=>g*4+i),bpm:120,origin:0,
  targets:Array.from({length:4},(_,i)=>1+g*2+i*.25+(i%2===0?.02+lo:-.02+hi)),errors:Array(4).fill(.02)}));
 const validate=fits=>{
  const notes=d.notes.map(n=>({...n,status:'excluded',target_seconds:null}));
  fits.forEach((f,g)=>f.targets?.forEach((t,i)=>{if(t!=null)Object.assign(notes[g*4+i],{target_seconds:t,status:'estimated'});}));
  const bad=new Set(spacingFailures(notes,spacing,d.scroll_motion).map(w=>w.note));
  return notes.flatMap((n,i)=>n.status==='estimated'&&!bad.has(i)?[i]:[]);
 };
 return {d,groups,validate};
}
for(const spacing of[20,40,80])for(const fps of[30,60,120])test(`native spacing resolves a phase between regular samples: ${spacing} spacing / ${fps} fps`,()=>{
 const {d,groups,validate}=fixture(spacing,fps),before=structuredClone({d,groups});
 const r=fitPhase(groups,.001,validate);
 assert.equal(r.status,'restored');assert.equal(r.consistent_notes.length,4);
 assert.ok(.0004-1e-9<=r.phase&&r.phase<=.0005+1e-9);
 assert.ok(r.phase_range[0]>=.0004-1e-9&&r.phase_range[1]<=.0005+1e-9);
 assert.equal(r.fits[0].split,2);assert.deepEqual(r.fits[0].rows,[4,5,6,7]);
 assert.deepEqual(validate(r.fits),[0,1,2,3]);assert.deepEqual({d,groups},before);
 for(const [i,t]of r.fits[0].targets.entries())assert.ok(Math.abs(t-groups[0].targets[i])<=.02+1e-9);
});
test('overlapping source phase intervals require their common interior, not separate per-group phases',()=>{
 const {groups,validate}=fixture(40,60,[[.0001,.0006],[.0005,.0009]]),r=fitPhase(groups,.001,validate);
 assert.equal(r.status,'restored');assert.equal(r.consistent_notes.length,8);
 assert.ok(.0005-1e-9<=r.phase&&r.phase<=.0006+1e-9);
 assert.ok(r.fits.every(f=>f.split===2));
});
test('disjoint source intervals cannot produce a fully supported common phase',()=>{
 const {groups,validate}=fixture(40,60,[[.0001,.0003],[.0006,.0008]]),r=fitPhase(groups,.001,validate);
 assert.ok(r.status==='failed'||r.consistent_notes.length<8);
});
test('a feasible phase outside the alignment interval is never proposed',()=>{
 const {groups,validate}=fixture(40,60,[[.0011,.0012]]),r=fitPhase(groups,.001,validate);
 assert.ok(r.status==='failed'||r.consistent_notes.length<4);
 assert.ok(r.phase_trials.every(p=>-.001<=p.phase_seconds&&p.phase_seconds<=.001));
});

for(const sign of[-1,1])test(`row rounding tolerance cannot expand the alignment budget: sign ${sign}`,()=>{
 const uncertainty=.001,groups=[{targets:[1+sign*(uncertainty+1e-9)],errors:[0],bpm:120,origin:0}];
 const r=fitPhase(groups,uncertainty);
 assert.ok(r.phase_trials.every(p=>-uncertainty<=p.phase_seconds&&p.phase_seconds<=uncertainty));
 if(r.status==='restored'){
  assert.ok(-uncertainty<=r.phase&&r.phase<=uncertainty);
  for(const range of[r.phase_range,r.source_phase_range]){
   assert.ok(range[0]<=range[1]);assert.ok(-uncertainty<=range[0]&&range[1]<=uncertainty);
  }
 }
});
