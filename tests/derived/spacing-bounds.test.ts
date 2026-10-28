import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene} from './fixtures.ts';
import {prepare} from '../../src/piu_timeline/derived/beats/coordinates.ts';
import {spacingFailures} from '../../src/piu_timeline/derived/beats/spacing.ts';

function scene(spacing:number,errors:number[]){
  const d=nativeScene([[.85,0],[.95,1],[.6,2],[.7,3],[.8,4],[1,2],[1.1,3],[1.2,4]],spacing);
  for(const [i,error]of errors.entries()){
    d.notes[i].points=d.notes[i].points.map(([t,y])=>[t,y+error*spacing]);
    d.scroll_motion.coordinate_registration.chunks[0].head_offsets[i].offset_pixels+=error*spacing;
  }
  return d;
}
for(const spacing of [20,40,80]){
  test(`independent endpoint bounds apply to both measured heads at spacing ${spacing}`,()=>{
    const d=scene(spacing,[.02,-.02]),before=structuredClone(d);
    const failures=spacingFailures(d.notes,spacing,d.scroll_motion,prepare(d,spacing));
    assert.deepEqual(failures,[],'opposite in-budget errors must not become a pair conflict');
    assert.deepEqual(d,before);
  });
  test(`a correct relative gap cannot hide a common absolute error at spacing ${spacing}`,()=>{
    const d=scene(spacing,[.1,.1]);
    const failures=spacingFailures(d.notes,spacing,d.scroll_motion,prepare(d,spacing));
    assert.deepEqual(failures.filter(w=>w.peer_notes.join(',')==='0,1').map(w=>w.note).sort(),[0,1]);
  });
  test(`independent references attribute an actual coordinate conflict at spacing ${spacing}`,()=>{
    const d=scene(spacing,[.1,0]);
    const failures=spacingFailures(d.notes,spacing,d.scroll_motion,prepare(d,spacing));
    assert.deepEqual(failures.filter(w=>w.peer_notes.join(',')==='0,1').map(w=>w.note),[0]);
  });
}

for(const spacing of [20,40,80])for(const gap of [0,1/128,1/96]){
  test(`close heads retain absolute coordinate validation: spacing=${spacing}, gap=${gap}`,()=>{
    const events:[number,number][]=[[.85,0],[.85+gap,1],[.6,2],[.7,3],[.8,4],[1,2],[1.1,3],[1.2,4]];
    const d=nativeScene(events,spacing),before=structuredClone(d);
    assert.deepEqual(spacingFailures(d.notes,spacing,d.scroll_motion,prepare(d,spacing)),[]);
    // Shift only proposed timing; keep the independently sampled image evidence.
    for(const i of [0,1])d.notes[i].target_seconds+=.025;
    const failures=spacingFailures(d.notes,spacing,d.scroll_motion,prepare(d,spacing));
    assert.deepEqual(failures.filter(w=>w.peer_notes.join(',')==='0,1').map(w=>w.note).sort(),[0,1]);
    assert.deepEqual(d.notes.map(n=>n.points),before.notes.map(n=>n.points));
  });
}
