import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeScene} from '../fixtures.ts';
import {contracts} from '../../../src/piu_timeline/derived/contracts.ts';
import {prepare} from '../../../src/piu_timeline/derived/beats/chords.ts';

function scene(spacing:number,gap=.0125){
 const velocity=6*spacing,d=nativeScene([[.85,0],[.85+gap*spacing/velocity,1]],spacing,60);
 d.notes.forEach((n,i)=>{n.points=n.points.map(([t,y])=>[t,y+(i?1:-1)*.0125*spacing]);});
 d.head_registration={format:{native_cap_registration:structuredClone(contracts.native_anchor)},
  notes:d.notes.map((n,i)=>({note:i,coordinate_method:'native_image_anchors',observations:n.points.map(([time,y])=>({
   time,source_pts_seconds:80+time,native_y_pixels:y,template:`independent-full-cap-${i}`,
   native_cap_reference_scale_y:spacing/80,native_cap_coordinate_uncertainty_pixels:spacing/80}))}))};
 return d;
}
for(const spacing of[20,40,80])test(`certified endpoint bounds retain the same physical gap at spacing ${spacing}`,()=>{
 const d=scene(spacing),before=structuredClone(d),proofs=prepare(d,spacing);
 assert.equal(proofs.length,1);
 const p=proofs[0];assert.ok(p.maximum_gap_pixels>contracts.chords.maximum_gap_spacing*spacing);
 assert.ok(p.native_gap_range_pixels[0]<=.0125*spacing+1e-8&&p.native_gap_range_pixels[1]>=.0125*spacing-1e-8);
 assert.ok(p.endpoint_uncertainty_pixels.every(pair=>pair.every(e=>e===spacing/80)));
 assert.deepEqual(d,before);
 assert.deepEqual(prepare(scene(spacing,.1),spacing),[],'a real stagger outside the joint bounds remains separate');
 const bad=scene(spacing),r=bad.head_registration.notes[1],sample=r.observations[4];
 bad.notes[1].points[4][1]+=.15*spacing;sample.native_y_pixels+=.15*spacing;
 assert.deepEqual(prepare(bad,spacing),[],'one incompatible native frame cannot be hidden by a median');
});
