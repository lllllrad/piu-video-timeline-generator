import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {project} from '../../../src/piu_timeline/derived/skins/centers.ts';

test('per-frame source centers retain raw positions and never infer an unmeasured offset',()=>{
 const raw=[[1,100],[2,80],[3,60]],before=structuredClone(raw);
 const record={status:'measured_only',offset_pixels:8,observations:[
  {time:1,detected_y_pixels:100,offset_pixels:2},{time:3,detected_y_pixels:60,offset_pixels:-1}]};
 assert.deepEqual(project(raw,record),[[1,102],[2,80],[3,59]]);
 assert.deepEqual(raw,before);
 for(const observations of [[...record.observations,record.observations[0]],
  [{time:4,detected_y_pixels:40,offset_pixels:1}],
  [{time:1,detected_y_pixels:101,offset_pixels:1}],
  [{time:1,detected_y_pixels:100,offset_pixels:NaN}]]){
  assert.throws(()=>project(raw,{...record,observations}));
 }
});

const native=String.raw`
import json,tempfile
from pathlib import Path
from copy import deepcopy
from tests.play.skins.test_anchor_registration import fixture,register,chord_trace
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.replay import detector_metadata
from piu_timeline.play.skins.reuse import reusable_groups
from piu_timeline.play.skins.coordinates import measure
from piu_timeline.play.head_registration import apply
from piu_timeline.play.beats.chords import prepare
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);rgb,data,manifest=fixture(root)
 # Matching anchors intentionally differ from the independently measured center.
 for t in manifest['templates'][:3]:t['native_center_pixels']=[t['anchor_pixels'][0],t['anchor_pixels'][1]+1]
 for n,r in zip(data['notes'],data['head_registration']['notes']):
  r['observations'][0]['offset_pixels']=2
 (root/'bank.json').write_text(json.dumps(manifest));(root/'analysis.json').write_text(json.dumps(data))
 (root/'head-registration.json').write_text(json.dumps(data['head_registration']))
 old=detector_metadata(root/'bank.json');path=register(root,rgb);bank=load_bank(path)
 assert reusable_groups({'skin_detector':old},bank)=={'caps/0','body/0'}
 trace,frames=chord_trace(path);trace.update(combo_events=[],unsupported_intervals=[])
 trace['layout']['note_y_max']=.95
 trace['scroll_motion']={'samples':[{'time':f['playback_seconds'],'source_pts':f['source_pts_seconds'],
  'phase':500*f['playback_seconds'],'chunk':0,'support':2,'variance':0}for f in frames]}
 raw=deepcopy(trace);original=deepcopy(frames)
 (root/'frames.jsonl').write_text(''.join(json.dumps(f)+'\n'for f in frames))
 registration=measure(trace,frames)
 assert registration['notes'][0]['observations'][0]['native_y_pixels']==trace['notes'][0]['points'][0][1]+1
 first=apply(trace,root);second=apply(first,root)
 assert frames==original and trace==raw
 for old,new,again in zip(raw['notes'],first['notes'],second['notes']):
  assert new['detected_points']==old['points']
  assert all(t==a and abs(v-y-1)<1e-10 for (t,v),(a,y)in zip(new['points'],old['points']))
  assert again['points']==new['points'] and again['detected_points']==old['points']
 assert prepare(first,40)[0]['measurement_basis']=='source_bound_native_cap_centers'
 # Resizing changes physical uncertainty in the same units as measured positions.
 smaller=deepcopy(trace);smaller['analysis_width']/=2
 assert measure(smaller,frames)['notes'][0]['observations'][0]['native_cap_coordinate_uncertainty_pixels']==.5
 # Center metadata is bound to its original source certificate.
 changed=json.loads(path.read_text());changed['templates'][0]['native_center_pixels'][1]+=.5
 path.write_text(json.dumps(changed))
 try:load_bank(path)
 except ValueError:pass
 else:raise AssertionError('changed center reused a stale certificate')
 print(json.dumps({'points':len(first['notes'][0]['points']),'source_pts':first['head_registration']['notes'][0]['observations'][0]['source_pts_seconds']}))
`;
test('source-certified centers refit timing without moving native image evidence or applying twice',()=>{
 const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',native],{encoding:'utf8'}));
 assert.equal(result.points,9);assert.equal(result.source_pts,50.6);
});
