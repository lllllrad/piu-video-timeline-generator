import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {accountCapCoverage} from '../../src/piu_timeline/derived/hold_coverage.ts';

const script=String.raw`
import json,tempfile,sys
from pathlib import Path
from copy import deepcopy
from tests.play.processing.fixtures import fixture
from piu_timeline.play.processing import observe_processing
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);case=sys.argv[1]
 data,times,pts=fixture(root,hud=False,hold=True,hidden_frames=(57,)if case=='missing_cap'else (),flash_frames=(57,)if case=='white_flash'else ())
 before=deepcopy(data);out=observe_processing(data,root/'processing-features.npz');assert data==before
 n=out['notes'][0]
 assert n['status']=='hold_component' and n['reason']=='use_sustained_body_state'
 assert n['samples'] and n['cap_coverage']
 assert n['cap_observation']['status']=='disappeared_near_receptor'
 assert all(p['playback_seconds']<1 for p in n['cap_coverage'])
 assert not any(s['state']=='present'for s in n['samples']if s['time']>=1), 'body alone cannot prove cap presence'
 if case!='clear':assert not any(p['playback_seconds']==57/60 for p in n['cap_coverage'])
 if case=='white_flash':assert any(s['time']==57/60 and s['state']=='unknown'and s['unknown_reason']=='white_effect'for s in n['samples'])
 assert len(out['notes'])==2 and all(p['status']=='hold_component'for p in out['notes'])
 for p in n['cap_coverage']:
  assert p['source_pts_seconds']==42+p['playback_seconds']
  assert isinstance(p['template_pose'],int)
  assert len(set(p['reference']['supporting_source_pts_seconds']))>=3
  assert p['intervals_pixels'] and all(p['box_pixels'][0]<=a<b<=p['box_pixels'][1] for a,b in p['intervals_pixels'])
 assert (root/'source.mkv').read_bytes()==b'unchanged recording'
 print(json.dumps({'data':data,'processing':out,'timeline':list(zip(times,pts))}))
`;
for(const scenario of ['clear','missing_cap','white_flash'])test(`native hold pixels retain cap evidence without body or flash false positives: ${scenario}`,()=>{
 const out=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script,scenario],{encoding:'utf8'}));
 const {data,processing}=out,n=processing.notes[0];
 assert.ok(n.cap_coverage.length>=3);assert.ok(n.samples.length>n.cap_coverage.length);
 // Consumer input comes from the actual native measurement, including its
 // reference poses, geometry and PTS; no independent fabricated cap proof.
 Object.assign(data.hold_analysis.holds[0],{image_connection_id:0,body_frames:8});
 const time=57/60;
 data.hold_analysis.unresolved_tracks=[{note:0,tail_note:1,lane:2,image_connection_id:0,reason:'unresolved_hold_geometry',
  failure_detail:'known_hold_image_connection_not_observed_in_clear_frames',visible_start_seconds:time,visible_end_seconds:time,observed_points:1,
  image_evidence:[{time,source_pts:42+time,missing_intervals_pixels:[[45,50]]}]}];
 data.visual_channels={timeline:{frames:out.timeline},processing};
 const result=accountCapCoverage(data);
 assert.equal(result.hold_analysis.unresolved_tracks.length,scenario==='clear'?0:1);
 if(scenario!=='clear')assert.deepEqual(result.hold_analysis.unresolved_tracks,data.hold_analysis.unresolved_tracks);
});
