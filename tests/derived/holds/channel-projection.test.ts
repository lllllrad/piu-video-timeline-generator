import test from 'node:test';
import {createHash}from 'node:crypto';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
const script=String.raw`
import json,tempfile
from pathlib import Path
from piu_timeline.play.channels import CHANNEL_FORMAT
from piu_timeline.play.observations.channel_projection import retained
from piu_timeline.play.observations.artifacts import files,file_identities
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);(root/'frames.jsonl').write_text('intentionally not JSON: must not parse the large source')
 (root/'frames.base.jsonl').write_text('same for baseline')
 data={'media':{'path':'recording.mkv','mtime_ns':1790000000000000001},'layout':{},'analysis_width':400,
       'analysis_height':300,'game_roi':[0,0,400,300],'frame_count':1,'frame_timeline':[{'time':1,'source_pts':81}]}
 (root/'analysis.json').write_text(json.dumps(data,indent=2))
 saved={'contract':{'format':CHANNEL_FORMAT,'traces':files(root,('frames.jsonl','frames.base.jsonl'))},
  'channels':{'timeline':{'frames':[[1,81]]},'popup':{'observation_fields':['combo','combo_confidence','baseline_combo','baseline_combo_confidence'],
  'observations':[[10,.9,9,.8]]},'motion':{'observations':[[[0,.2,.4,.95]]]}}}
 path=root/'visual-channels.json';path.write_text(json.dumps(saved))
 first=retained(data,root);changed=retained({**data,'game_roi':[0,0,800,600]},root)
 try:retained({**data,'frame_timeline':[{'time':1,'source_pts':82}]},root);bad=False
 except ValueError:bad=True
 (root/'frames.jsonl').write_text('changed original native bytes')
 stale=retained(data,root)
 (root/'identity.json').write_text(json.dumps({'path':str(root.resolve())+'/proof.json'}))
 print(json.dumps({'frames':first,'changed_geometry':changed,'changed_native':stale,'bad_pts':bad,
  'identity':file_identities(root,('identity.json',))['identity.json']}))
`;
test('channel assembly reuses unassigned source rows, rejects changed acquisition and preserves baseline independently',()=>{
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.deepEqual(r.frames,[{playback_seconds:1,source_pts_seconds:81,combo:10,combo_confidence:.9,
  baseline_combo:9,baseline_combo_confidence:.8,notes:[{lane:0,x:.2,y:.4,quality:.95}]}]);
 assert.equal(r.changed_geometry,null);assert.equal(r.changed_native,null);assert.equal(r.bad_pts,true);
 assert.equal(r.identity.sha256,createHash('sha256').update('{"path": "@segment/proof.json"}').digest('hex'));
});
