import test from 'node:test';
import assert from 'node:assert/strict';
import {resolve}from '../../../src/piu_timeline/derived/tracking/deferred.ts';
import {assign}from '../../../src/piu_timeline/derived/frame_tracking.ts';
const position=(y:number)=>({yPixels:y,uncertaintyPixels:0,basis:{kind:'native_cap_center' as const}});
const sample=(time:number,y:number,role='hold_start')=>({time,sourcePtsSeconds:80+time,
 coordinateSampling:'sampled_image_grid' as const,capRole:role,center:position(y),anchor:position(y)});
const fragment=(id:number,first:number,offset=0,count=4)=>({id,lane:0,
 observations:Array.from({length:count},(_,i)=>sample((first+i)/60,200-1.5*(first+i)+offset))});
const edges=[{from:0,to:1,time:4/60},{from:0,to:2,time:4/60}];

test('an unresolved edge waits for future observations rather than choosing its closest candidate',()=>{
 const past=fragment(0,0),correct=fragment(1,4,0,1),wrong=fragment(2,4,7,1);
 assert.equal(resolve([past,correct,wrong],edges).length,3);
 correct.observations=fragment(1,4).observations;wrong.observations=fragment(2,4,7).observations;
 const input=[past,correct,wrong],before=structuredClone(input),groups=resolve(input,edges);
 assert.deepEqual(groups.map(g=>g.indices),[[0,1],[2]]);assert.deepEqual(input,before);
 const proof=groups[0].connections[0];assert.equal(proof.method,'deferred_native_approaches');
 assert.equal(proof.endpoint_uncertainty_pixels,0);assert.equal(proof.observed_render_step_pixels,1.5);
 assert.equal(proof.references.length,8);
 assert.ok(proof.alternatives.some(a=>a.status==='refuted'&&a.reason==='past_and_future_motion_incompatible'));
});

test('an unrefuted competing identity prevents a merge even when one candidate is closer',()=>{
 const tracks=[fragment(0,0),fragment(1,4),fragment(2,4,.5)];
 assert.equal(resolve(tracks,edges).length,3);
});
for(const mode of ['role','source','gap','time','reverse'])test(`unsupported deferred identity remains separate: ${mode}`,()=>{
 const a=fragment(0,0),b=fragment(1,4);
 if(mode==='role')b.observations.forEach(o=>o.capRole='hold_end');
 if(mode==='source')b.observations[2].sourcePtsSeconds+=.1;
 if(mode==='gap')b.observations.forEach(o=>{o.time+=.1;o.sourcePtsSeconds+=.1});
 if(mode==='time')b.observations[0].time=a.observations.at(-1).time;
 if(mode==='reverse')b.observations.forEach((o,i)=>{o.center=position(220+i*2);o.anchor=o.center});
 assert.equal(resolve([a,b],[edges[0]]).length,2);
});

test('input times and receptor effects are absent from deferred identity evidence',()=>{
 const tracks=[fragment(0,0),fragment(1,4)],a=resolve(tracks,[edges[0]]);
 const changed=tracks.map(t=>({...t,target_seconds:Math.random()*100,judgment:'MISS',input_seconds:0}));
 assert.deepEqual(resolve(changed,[edges[0]]),a);
});

test('independently sampled cap steps do not have to be one exact engine translation',()=>{
 const time=1+1/60,tracks=[0,1,2].map(lane=>({lane,maximumGapSeconds:.12,
  observations:Array.from({length:6},(_,i)=>sample(1-(5-i)/60,180+30*lane+5-i))}));
 const caps=tracks.map((t,lane)=>({lane,observation:sample(time,t.observations.at(-1).center.yPixels-[.75,1,1.5][lane])}));
 const before=structuredClone({tracks,caps}),r=assign(tracks,caps,time,40);
 assert.deepEqual(r.matches,[[0,0],[1,1],[2,2]]);assert.deepEqual({tracks,caps},before);
 assert.ok(caps.every(d=>d.observation.center.uncertaintyPixels===0));
});

test('observed hold starts and ends cannot exchange identities in a dense lane',()=>{
 const tracks=[{lane:0,maximumGapSeconds:.12,observations:[sample(1,200,'hold_start')]},
 {lane:0,maximumGapSeconds:.12,observations:[sample(1,204,'hold_end')]}],time=1+1/60;
 const caps=[{lane:0,observation:sample(time,199,'hold_start')},{lane:0,observation:sample(time,203,'hold_end')}];
 assert.deepEqual(assign(tracks,caps,time,40).matches,[[0,0],[1,1]]);
});

const visibility={width:400,height:400,capHeightPixels:20,occluders:[],layout:{receptor_y:.1,note_y_max:.95,
 lanes:Array.from({length:5},(_,i)=>({x:.1+.15*i}))}};
test('persistent visible order resolves a complete dense sampled scene without maximizing match count',()=>{
 const time=1+1/60,tracks=[0,1].flatMap(lane=>[200,208].map(y=>({lane,maximumGapSeconds:.12,observations:[sample(1,y,'tap')]}))),
 caps=tracks.map(t=>({lane:t.lane,observation:sample(time,t.observations[0].center.yPixels-1,'tap')}));
 const r=assign(tracks,caps,time,40,[],[],visibility);
 assert.deepEqual(r.matches,[[0,0],[1,1],[2,2],[3,3]]);
 assert.equal(r.constellationReference.method,'complete_sampled_source_constellation');
});
test('simultaneous processing and new entry cannot masquerade as a full repeating scene',()=>{
 const time=1+1/60,ys=Array.from({length:11},(_,i)=>50+30*i),
 tracks=[0,1].flatMap(lane=>ys.map(y=>({lane,maximumGapSeconds:.12,observations:[sample(1,y,'tap')]}))),
 caps=tracks.map(t=>({lane:t.lane,observation:sample(time,t.observations[0].center.yPixels+10,'tap')}));
 const r=assign(tracks,caps,time,40,[],[],visibility);
 assert.equal(r.constellationReference,null);assert.deepEqual(r.matches,[]);assert.ok(r.ambiguities.length);
});
test('a known HUD may hide replacement caps, while its positive observations remain candidates',()=>{
 const time=1+1/60,tracks=[0,1].flatMap(lane=>[200,208].map(y=>({lane,maximumGapSeconds:.12,observations:[sample(1,y,'tap')]}))),
 caps=tracks.map(t=>({lane:t.lane,observation:sample(time,t.observations[0].center.yPixels-1,'tap')})),
 geometry={...visibility,occluders:[{id:'judgment_word',rect:[0,.4,1,.2]}]};
 const r=assign(tracks,caps,time,40,[],[],geometry);
 assert.equal(r.constellationReference,null);assert.deepEqual(r.matches,[]);assert.ok(r.ambiguousDetections.length);
});

function independentlyObservedScene(){
 const tracks=[fragment(0,3,0,1),fragment(1,4,0,1),fragment(2,4,7,1),
  {...fragment(3,0,40,9),lane:1},{...fragment(4,0,80,9),lane:2}];
 const timeline=Array.from({length:9},(_,i)=>({time:i/60,source_pts:80+i/60}));
 return {tracks,timeline};
}
test('independent approaches in two other lanes resolve short provisional fragments without target clocks',()=>{
 const {tracks,timeline}=independentlyObservedScene(),before=structuredClone(tracks),groups=resolve(tracks,edges,timeline,40);
 assert.deepEqual(groups.map(g=>g.indices),[[0,1],[2],[3],[4]]);
 const proof=groups[0].connections[0];assert.equal(proof.method,'deferred_independent_native_clock');
 assert.equal(proof.endpoint_uncertainty_pixels,0);assert.equal(new Set(proof.references.map(r=>r.lane)).size,2);
 assert.ok(proof.velocity_range_pixels_per_second[0]<=90&&90<=proof.velocity_range_pixels_per_second[1]);
 assert.deepEqual(tracks,before);
});
for(const mode of ['one-lane','contradictory-speed','broken-source'])
test(`short fragments cannot bootstrap their own independent motion: ${mode}`,()=>{
 const {tracks,timeline}=independentlyObservedScene();
 if(mode==='one-lane')tracks.pop();
 if(mode==='contradictory-speed')tracks[4].observations.forEach((o,i)=>{o.center=position(280-7.5*i);o.anchor=o.center});
 if(mode==='broken-source')tracks[1].observations[0].sourcePtsSeconds+=.01;
 const groups=resolve(tracks,edges,timeline,40);
 assert.equal(groups.length,tracks.length);assert.ok(groups.every(g=>g.connections.length===0));
});
test('a repeated game image keeps original PTS and capture-phase uncertainty without widening its position',()=>{
 const {tracks,timeline}=independentlyObservedScene();
 tracks[1].observations[0]=sample(4/60,tracks[0].observations[0].center.yPixels);
 for(const ref of tracks.slice(3)){
  ref.observations[4].center=ref.observations[3].center;ref.observations[4].anchor=ref.observations[3].anchor;
 }
 const groups=resolve(tracks,edges,timeline,40),proof=groups[0].connections[0];
 assert.deepEqual(groups[0].indices,[0,1]);assert.equal(proof.endpoint_uncertainty_pixels,0);
 assert.deepEqual(proof.source_pts_seconds,[80+3/60,80+4/60]);
 assert.ok(Math.abs(proof.source_capture_period_seconds-1/60)<1e-12);
});


test('a HUD does not fragment a separate fully visible dense zone',()=>{
 const time=1+1/60,tracks=[0,1].flatMap(lane=>[200,208,300].map(y=>({lane,maximumGapSeconds:.12,observations:[sample(1,y,'tap')]}))),
 caps=tracks.filter(t=>t.observations[0].center.yPixels<250).map(t=>({lane:t.lane,observation:sample(time,t.observations[0].center.yPixels-1,'tap')})),
 geometry={...visibility,occluders:[{id:'judgment_word',rect:[0,.7,1,.1]}]};
 const r=assign(tracks,caps,time,40,[],[],geometry);
 assert.deepEqual(r.matches,[[0,0],[1,1],[3,2],[4,3]]);
 assert.equal(r.constellationReference.method,'complete_sampled_source_constellation');
});
