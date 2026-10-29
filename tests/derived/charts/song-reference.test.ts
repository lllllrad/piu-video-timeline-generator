import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const script=String.raw`
import json,tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from piu_timeline.charts.ucs import parse
from piu_timeline.charts.reference import prepare,retained
from piu_timeline.play.beats.timing import reference
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);repo=root/'charts';repo.mkdir();out=root/'source/play/segment-001';out.mkdir(parents=True)
 (repo/'catalog.json').write_text(json.dumps({'songs':[{'index':'CS101','title':'Example Song','bpm':'120'}]}))
 (repo/'aliases.json').write_text(json.dumps({'예시곡':{'index':'CS101','title':'예시 곡','basis':'official_localized_catalogue'}}))
 source=root/'recording.mkv';source.write_bytes(b'unchanged original recording');music=root/'reference.mp3';music.write_bytes(b'independent reference')
 media={'path':str(source),'size_bytes':source.stat().st_size,'mtime_ns':source.stat().st_mtime_ns}
 data={'song':'예시 곡','chart':'D24','segment_number':1,'media':media,'start_seconds':10,'end_seconds':30,
       'skin_detector':{'registration_reviewed':False},'notes':[]}
 document=parse(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*16)
 class Provider:
  def template(self,code):return document,music,'https://official.example/'+code
 alignment={'method':'reference_audio_translation','song_start_seconds':10.02,'uncertainty_seconds':.01,'rate':1}
 with patch('piu_timeline.charts.audio.align',return_value=alignment),patch('piu_timeline.play.support.require_chart_geometry',side_effect=AssertionError('timing must not require UCS geometry')):
  first=prepare(data,out,repo,Provider())
 with patch('piu_timeline.charts.reference.Client',side_effect=AssertionError('unchanged reference must not download or decode')):
  second=prepare(data,out,repo)
 with patch('piu_timeline.charts.data.default_repository',return_value=repo):resolved=reference(data,out)
 invalid=[]
 for case in ('source_window','identity','reference_audio','timing'):
  changed=deepcopy(data);code='CS101';audio=music.read_bytes();timing=(repo/'timing/CS101.ucs').read_bytes()
  if case=='source_window':changed['start_seconds']+=1
  elif case=='identity':code='CS102'
  elif case=='reference_audio':music.write_bytes(b'different reference')
  else:(repo/'timing/CS101.ucs').write_bytes(b'different timing')
  invalid.append(retained(changed,out,repo,code)is None)
  music.write_bytes(audio);(repo/'timing/CS101.ucs').write_bytes(timing)
 source.write_bytes(b'changed recording')
 invalid.append(retained(data,out,repo,'CS101')is None)
 print(json.dumps({'same':first==second,'resolved':resolved,'invalid':invalid,
  'draft_created':(repo/'charts').exists(),'skin_reviewed':data['skin_detector']['registration_reviewed']}))
`;
const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
test('official timing prepares and reuses a source-bound alignment before skin/UCS registration',()=>{
 assert.equal(result.same,true);assert.equal(result.draft_created,false);assert.equal(result.skin_reviewed,false);
 assert.equal(result.resolved.status,'available');assert.equal(result.resolved.ucs_index,'CS101');
 assert.equal(result.resolved.song_start_seconds,10.02);assert.equal(result.resolved.alignment_uncertainty_seconds,.01);
});
test('source, window, identity, official timing and reference audio changes invalidate retained alignment',()=>{
 assert.deepEqual(result.invalid,[true,true,true,true,true]);
});
