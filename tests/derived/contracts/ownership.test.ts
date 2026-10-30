/** Public stage contracts enforce ownership independently of numerical fixtures. */
import test from 'node:test';import assert from 'node:assert/strict';
import {capture,materialize as coordinateView} from '../../../src/piu_timeline/derived/stages/coordinates.ts';
import {resolve as nativeTiming} from '../../../src/piu_timeline/derived/stages/native_timing.ts';
import {artifact} from '../../../src/piu_timeline/derived/stages/contracts.ts';
import {changes,apply} from '../../../src/piu_timeline/derived/stages/notes.ts';
import {input,reconstruct,materialize as beatView} from '../../../src/piu_timeline/derived/beats/stage.ts';
import {counters,judgmentInput,judgments} from '../../../src/piu_timeline/derived/stages/associations.ts';
import {input as inspectionInput,calculationView} from '../../../src/piu_timeline/derived/pipeline/contracts.ts';
import {prepare,preview} from '../../../src/piu_timeline/derived/pipeline/presentation.ts';
import {materialize,result,applyResult} from '../../../src/piu_timeline/derived/pipeline/composition.ts';
import {domain} from '../beats/fixtures.ts';
import {processing} from '../../../src/piu_timeline/derived/pipeline/inputs.ts';
import {derive} from '../../../src/piu_timeline/derived/cli.ts';
test('coordinate result contains no HUD associations and owns no raw detection edits',()=>{
 const data={...domain(),combo_events:[{delta:1}],matches:[{note:0}],coverage:{timed:1}},before=structuredClone(data),source=capture(data);
 assert.deepEqual(Object.keys(source.coordinates.data).sort(),['head_registration','notes','scroll_motion']);assert.ok(!Object.hasOwn(source.observations.data,'matches'));
 assert.ok(Object.isFrozen(source.observations.data.notes[0].detection_points));assert.throws(()=>{(source.observations.data.notes[0] as {lane:number}).lane=9;},TypeError);
 const view=coordinateView(source);view.notes[0].points[0][1]++;assert.deepEqual(data,before);assert.notDeepEqual(view.notes[0].points,source.coordinates.data.notes[0].values.points);
 assert.throws(()=>coordinateView({...source,coordinates:artifact('coordinates',{...source.coordinates.data,matches:[]})}),/Foreign/);
 assert.throws(()=>coordinateView({...source,coordinates:artifact('beats',source.coordinates.data) as never}),/Expected coordinates/);
});
test('native and beat artifacts are separate owned patches with explicit composition',()=>{
 const source=capture(domain()),native=nativeTiming(source),request=input(source,native,{status:'available',song_start_seconds:1,alignment_uncertainty_seconds:0},':Format=1\n:Mode=Single\n:BPM=120\n:Beat=4\n:Split=4\n'+'.....\n'.repeat(32)),before=structuredClone(request),r=reconstruct(request);
 assert.equal(native.stage,'native-timing');assert.equal(r.stage,'beats');assert.ok(!Object.hasOwn(r.data,'layout'));assert.ok(!Object.hasOwn(r.data,'matches'));assert.ok(r.data.notes.every(n=>!Object.hasOwn(n.values,'points')&&!Object.hasOwn(n.values,'lane')));
 const view=beatView(request,r);assert.equal(view.notes[4].target_seconds,1.5);assert.deepEqual(request,before);
 assert.throws(()=>beatView(request,artifact('beats',{...r.data,notes:[{note:0,values:{points:[]},removed:[]}]})),/foreign/);
 assert.throws(()=>beatView(request,artifact('coordinates',r.data)as never),/Expected beats/);
});
test('generic ownership guard rejects changes of coordinates, lane, IDs and foreign deletions',()=>{
 const before=[{lane:0,points:[[1,2]],target_seconds:1}];
 for(const patch of [{lane:1},{points:[[1,3]]}])assert.throws(()=>changes(before,[{...before[0],...patch}],['target_seconds']),/unowned/);
 assert.throws(()=>changes(before,[],['target_seconds']),/identities/);
 assert.throws(()=>apply(before,[{note:0,values:{},removed:['lane']}],['target_seconds']),/foreign/);
 assert.throws(()=>apply(before,[{note:9,values:{target_seconds:2},removed:[]}],['target_seconds']),/identities/);
});
test('counter association accepts only timing and cannot return coordinate fields',()=>{
 const request={schema:1 as const,notes:[{lane:0,status:'estimated',target_seconds:1,prediction_uncertainty_seconds:.01}],events:[{status:'candidate',before:3,after:4,delta:1,lower_seconds:.99,upper_seconds:1.01}],display_delay_seconds:0,unsupported_intervals:[]},before=structuredClone(request),r=counters(request);
 assert.deepEqual(r.data.matches.map(m=>m.note),[0]);assert.ok(!Object.hasOwn(r.data,'notes'));assert.deepEqual(request,before);
 assert.throws(()=>counters({...request,notes:[{...request.notes[0],points:[[1,2]]}]}as never),/outside timing/);
});
function inspection(){return inspectionInput({...domain(),start_seconds:0,end_seconds:3,matches:[],combo_events:[],judgment_events:[],hold_analysis:{holds:[]},limitations:[]},{frames:[],visibility_frames:[],occluders:[],native_body_risk_available:false,pre_hold_proofs:{}});}
test('inspection scopes keep metadata out of inference and preserve channels',()=>{
 const request=inspection(),before=structuredClone(request);request.source.metadata={title:'opaque',media:{mtime_ns:1234567890123456789n}};
 const calculation=calculationView(request.source);assert.ok(!Object.hasOwn(calculation,'media'));assert.ok(!Object.hasOwn(calculation,'title'));
 const r=prepare(request),view=materialize(request,r);assert.equal(r.stage,'inspection');assert.equal(view.title,'opaque');assert.equal(view.media.mtime_ns,1234567890123456789n);
 assert.deepEqual(request.source.channels,before.source.channels);assert.deepEqual(request.source.tracks,before.source.tracks);assert.deepEqual(request.observations,before.observations);
 assert.deepEqual(derive('inspection-view',{request,result:r}),view);
});
test('inspection rejects missing, duplicate, reordered and foreign stage results',()=>{
 const request=inspection(),r=prepare(request),stages=r.data.stages;
 for(const wrong of [stages.slice(1),[...stages,stages[0]],[stages[1],stages[0],...stages.slice(2)]])assert.throws(()=>materialize(request,artifact('inspection',{stages:wrong})),/Incomplete|order/);
 assert.throws(()=>result('timing-ranges',{notes:[]},{notes:[],layout:{}}),/Unowned/);
 assert.throws(()=>result('hold-view',{notes:[{lane:0,points:[[1,2]]}]},{notes:[{lane:1,points:[[1,2]]}]}),/unowned/);
 const p=preview(request);assert.deepEqual(p.data.stages.map(s=>s.stage),['hold-view','motion-effects']);assert.ok(materialize(request,p).notes);
});

test('configured native evidence validates exact source identity outside numerical scopes',()=>{
 const request=inspection();request.source.metadata={media:{path:'/missing/source.mkv',mtime_ns:1234567890123456789n},game_roi:[0,0,800,600]};
 const view=materialize(request,preview(request));request.observations={...request.observations,configured_processing:{input:processing(view),output:{notes:[]}}};
 assert.ok(prepare(request));
 const other=structuredClone(request);other.source.metadata={...other.source.metadata,media:{path:'/missing/other.mkv'}};assert.throws(()=>prepare(other),/different interpretation inputs/);
});

test('policy composition preserves native hold details outside its compact input',()=>{
 const request=inspection();
 const base=calculationView(request.source);base.hold_analysis={holds:[],receptor_runs:[],native_geometry:{source_pts_seconds:[80,81]}};
 const before=structuredClone(base),policy=result('policy-view',base,{hold_analysis:{holds:[]}});
 const composed=applyResult(base,policy);assert.deepEqual(composed.hold_analysis.native_geometry,{source_pts_seconds:[80,81]});assert.deepEqual(base,before);
});

test('judgment input excludes image coordinates and cannot return timing edits',()=>{
 const source={notes:[{lane:0,status:'estimated',target_seconds:1,prediction_uncertainty_seconds:.01,points:[[.9,100]]}],matches:[],combo_events:[],media:{path:'/source.mkv'}},before=structuredClone(source);
 const request=judgmentInput(source,[],[]),r=judgments(request);assert.ok(!Object.hasOwn(request.source.data,'media'));assert.ok(!Object.hasOwn(request.source.data.notes[0],'points'));assert.ok(!Object.hasOwn(r.data,'notes'));assert.deepEqual(source,before);
 assert.throws(()=>judgments({...request,source:artifact('judgment-input',{...request.source.data,media:{}})}),/Foreign fields/);
});
