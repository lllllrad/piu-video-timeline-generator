import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fitTrajectory} from '../../src/piu_timeline/derived/coordinates/points.ts';
import {steps} from '../../src/piu_timeline/derived/holds/image_motion.ts';
const timeline = [{time: 1, source_pts: 41}, {time: 1.025, source_pts: 41.025}];
const peer = (delta = 5) => ({motion_trajectory:fitTrajectory({points:[[1,150],[1.025,150-delta]]})});
test('motion uses cap identity independently of tap/hold classification or successful timing', () => {
  assert.deepEqual(steps([peer()], [], timeline, 20), [{time: 1.025,
    method: 'identified_cap_displacement', displacement_pixels: 5, source_pts_range: [41, 41.025], source_notes: [0]}]);
});
test('conflicting cap motion, duplicate identities, absent peers and capture gaps cannot supply a link', () => {
  assert.deepEqual(steps([peer(), peer(8)], [], timeline, 20), []);
  assert.deepEqual(steps([{...peer(), duplicate_of: 0}], [], timeline, 20), []);
  assert.deepEqual(steps([{motion_trajectory:fitTrajectory({points:[[1,150]]})}, {motion_trajectory:fitTrajectory({points:[[1.025,145]]})}], [], timeline, 20), []);
  assert.deepEqual(steps([peer()], [], [timeline[0], {time: 1.1, source_pts: 41.1}], 20), []);
  assert.deepEqual(steps([peer(-2)], [], timeline, 20), []);
  assert.deepEqual(steps([peer(20)], [], timeline, 20), []);
});
test('registered motion stays authoritative and failed coordinate blocks forbid peer fallback', () => {
  const samples = [{time: 1, chunk: 0, support: 2, phase: 0}, {time: 1.025, chunk: 0, support: 2, phase: 6}];
  const registered = steps([peer()], samples, timeline, 20)[0];
  assert.equal(registered.displacement_pixels, 6);
  assert.equal(registered.method, 'registered_frame_displacement');
  assert.deepEqual(steps([peer()], samples.map(s => ({...s, coordinate_status: 'failed'})), timeline, 20), []);
  assert.throws(() => steps([peer()], [], [timeline[1], timeline[0]], 20), /timeline/);
});
const nativeScript = String.raw`
import copy,json,tempfile
from pathlib import Path
from tests.play.skins.test_temporal import fixture
from piu_timeline.play.skins.holds import measure_connections
from piu_timeline.play.skins.observations import observe
with tempfile.TemporaryDirectory()as tmp:
 data,frames,_=fixture(Path(tmp),unknown_peer=True)
 warnings=[];connections=measure_connections(data,frames,warnings)
 records=observe(data,frames)['notes']
 baseline=copy.deepcopy(data);baseline['notes']=baseline['notes'][:2];baseline['scroll_motion']['samples'][60]['support']=2
 existing_warnings=[];measure_connections(baseline,frames,existing_warnings)
 print(json.dumps({'connections':connections,'warnings':warnings,'existing_warnings':existing_warnings,'peer':records[2]}))
`;
test('an RGB-observed untyped peer bridges a measured-motion hole in a longer-than-field hold', () => {
  const observed = JSON.parse(execFileSync('sh', ['scripts/run.sh', '.venv/bin/python', '-c', nativeScript], {encoding: 'utf8'}));
  assert.equal(observed.connections.length, 1);
  const hold = observed.connections[0];
  assert.deepEqual([hold.head_note, hold.tail_note], [0, 1]);
  assert.ok(observed.peer.observations.length >= 2);
  assert.ok(observed.peer.observations.every(o => o.role === 'unknown'));
  const links = hold.image_connection_evidence.filter(p => p.time === 1.5 && p.motion_link);
  assert.ok(links.length > 0);
  for (const p of links) {
    assert.equal(p.motion_link.method, 'identified_cap_displacement');
    assert.deepEqual(p.motion_link.source_notes, [2]);
    assert.deepEqual(p.motion_link.source_pts_range, [41.475, 41.5]);
    assert.ok(Math.abs(p.motion_link.displacement_pixels - 5) < 1e-9);
  }
  assert.deepEqual(observed.warnings, observed.existing_warnings, 'independent image-loss warnings remain unchanged');
  assert.ok(observed.warnings.every(w => w.image_evidence.every(p => p.time !== 1.5))); 
});
