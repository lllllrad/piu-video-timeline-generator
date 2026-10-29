import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {contracts} from '../../src/piu_timeline/derived/contracts.ts';
import {imagePosition,sameBasis} from '../../src/piu_timeline/derived/coordinates/measurements.ts';
import {detectionTrajectory,fitTrajectory} from '../../src/piu_timeline/derived/coordinates/points.ts';
import {TrajectoryCoordinates} from '../../src/piu_timeline/derived/coordinates/trajectories.ts';
import {steps} from '../../src/piu_timeline/derived/holds/image_motion.ts';
import {prepare as chords} from '../../src/piu_timeline/derived/beats/chords.ts';
import {motionWarnings,continuity} from '../../src/piu_timeline/derived/visibility.ts';
import {measuredGapScene,nativeScene} from './fixtures.ts';

const format={native_cap_registration:contracts.native_anchor};
const sample={time:1,source_pts_seconds:81,native_y_pixels:100,template:'cap',cap_reference_sha256:'reference',
 native_cap_coordinate_uncertainty_pixels:1,native_cap_reference_scale_y:1};

test('one reader distinguishes reference anchors, measured centers, bounded conflicts and invalid positions',()=>{
 assert.equal(imagePosition(sample,100,format).kind,'native_cap_center');
 const raw={...sample};delete raw.native_cap_coordinate_uncertainty_pixels;
 assert.equal(imagePosition(raw,100,format).kind,'image_reference_anchor');
 const conflict={...raw,native_cap_registration_status:'conflicting',native_cap_projection_uncertainty_pixels:2,native_cap_reference_template:'cap'};
 assert.equal(imagePosition(conflict,100,format).kind,'conflicting_center_projection');
 for(const bad of[{...sample,native_y_pixels:NaN},{...sample,native_y_pixels:101},
  {...sample,native_cap_coordinate_uncertainty_pixels:2},{...sample,source_pts_seconds:NaN}])assert.equal(imagePosition(bad,100,format).kind,'unavailable');
 assert.equal(imagePosition(sample,100,{}).kind,'unavailable');
 assert.equal(imagePosition({...conflict,native_cap_projection_uncertainty_pixels:.5},100,format).kind,'unavailable');
 assert.equal(sameBasis({kind:'native_cap_center'},{kind:'image_reference_anchor',reference:{kind:'sha256',value:'reference'}}),false);
});

test('a registered status without an explicit coordinate method never implies a center',()=>{
 const d=nativeScene([[1,0]]);delete d.head_registration.notes[0].coordinate_method;
 assert.deepEqual(new TrajectoryCoordinates(d.notes,d.head_registration,d.scroll_motion).basis(0),
  {kind:'unavailable',reason:'missing_coordinate_registration'});
});

test('a broad center interval cannot share the raw matching-origin chord model',()=>{
 const d=measuredGapScene(40);d.notes[1].points=structuredClone(d.notes[0].points);
 for(const [i,r]of d.head_registration.notes.entries())for(const o of r.observations){
  o.native_y_pixels=new Map(d.notes[i].points).get(o.time)??o.native_y_pixels;o.cap_reference_sha256='same-image';
  if(i===0){o.native_cap_reference_scale_y=2;o.native_cap_coordinate_uncertainty_pixels=2;}
  else delete o.native_cap_coordinate_uncertainty_pixels;
 }
 // Use identical capture times so only the coordinate frame distinguishes the pair.
 d.head_registration.notes[1].observations=d.head_registration.notes[0].observations.map(o=>{
  const raw={...o};delete raw.native_cap_coordinate_uncertainty_pixels;return raw;
 });
 assert.deepEqual(chords(d,40),[]);
});

test('relative motion rejects an image-ownership view even when its numeric shape is valid',()=>{
 const note={points:[[1,100],[1.025,95]] as [number,number][],detected_points:[[1,150],[1.025,143]] as [number,number][]};
 const timeline=[{time:1,source_pts:81},{time:1.025,source_pts:81.025}];
 assert.equal(steps([{motion_trajectory:fitTrajectory(note)}],[],timeline,40)[0].displacement_pixels,5);
 const wrong=[{motion_trajectory:detectionTrajectory(note)}] as unknown as Parameters<typeof steps>[0];
 assert.throws(()=>steps(wrong,[],timeline,40),/fit trajectory/);
});

test('visibility uses original images while motion warnings use the fit trajectory',()=>{
 const d=nativeScene([[1,0]]),frames=d.notes[0].points.map(([time])=>({playback_seconds:time,source_pts_seconds:80+time}));
 const expected=[motionWarnings(d,frames,[]),continuity(d,frames,[])];
 d.notes[0].detected_points=structuredClone(d.notes[0].points);
 d.notes[0].points=d.notes[0].points.map(([t],i)=>[t,80+i*10]);
 const visibility=r=>({warnings:r.warnings.filter(w=>w.check==='note_visibility'),known_occlusions:r.known_occlusions,accounted_exits:r.accounted_exits});
 const changed=continuity(d,frames,[]);
 assert.deepEqual(visibility(changed),visibility(expected[1]));
 assert.ok(changed.native_motion_warnings.some(w=>w.reason==='reverse_scroll_motion'));
 // Pose-dependent image anchors do not replace the producer's motion trajectory.
 d.notes[0].points=structuredClone(d.notes[0].detected_points);
 d.notes[0].detected_points=d.notes[0].points.map(([t],i)=>[t,80+i*10]);
 assert.deepEqual(motionWarnings(d,frames,[]),expected[0]);
});

const native=String.raw`
import copy,json,tempfile
from pathlib import Path
from tests.play.skins.test_temporal import fixture
from piu_timeline.play.skins.temporal import measured_steps
with tempfile.TemporaryDirectory()as tmp:
 data,frames,_=fixture(Path(tmp),unknown_peer=True)
 before=measured_steps(data,frames)
 for note in data['notes']:
  note['detected_points']=[(t,y+40*t*t)for t,y in note['points']]
  note['target_seconds']=1000.
 after=measured_steps(data,frames)
 print(json.dumps({'before':before,'after':after}))
`;
test('native relative motion keeps fit positions separate from image ownership and targets',()=>{
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',native],{encoding:'utf8'}));
 assert.ok(Object.keys(r.before).length>0);assert.deepEqual(r.after,r.before);
});

const nativeRisk=String.raw`
import json,tempfile
from pathlib import Path
from tests.play.holds.test_risk_evidence import scenario
from piu_timeline.play.holds.risk_evidence import derive
with tempfile.TemporaryDirectory()as tmp:
 data,frames,bank=scenario(Path(tmp));sample=data['head_registration']['notes'][0]['observations'][0]
 sample.update(native_y_pixels=49.,native_cap_reference_scale_y=.5,native_cap_coordinate_uncertainty_pixels=.5)
 result=derive(data,frames,bank)
 print(json.dumps(result['frames'][0]['causes'][0]))
`;
test('pixel ownership uses the raw anchor while approach bounds use the scaled native center',()=>{
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',nativeRisk],{encoding:'utf8'}));
 assert.equal(r.state,'approaching');assert.equal(r.ownership.head.y_pixels,49);
 assert.equal(r.ownership.head.coordinate_uncertainty_pixels,.5);
});

test('a projected fit without its original detection trajectory fails explicitly',()=>{
 const broken={points:[[1,100]] as [number,number][],head_registration:{coordinate_method:'native_image_anchors',coordinate_status:'projected'}};
 assert.throws(()=>detectionTrajectory(broken),/missing original detected_points/);
 const data={...broken,detected_points:[[1,98]] as [number,number][]};
 assert.deepEqual(detectionTrajectory(data).points,[[1,98]]);assert.deepEqual(fitTrajectory(data).points,[[1,100]]);
 const script="from piu_timeline.play.observations.coordinates import detection_points; detection_points({'points':[(1,100)],'head_registration':{'coordinate_status':'projected'}})";
 assert.throws(()=>execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{stdio:'pipe'}),/missing original detected_points/);
});
