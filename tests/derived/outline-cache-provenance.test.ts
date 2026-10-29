import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const script=String.raw`
import json,os,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from tests.play.skins.test_detector import examples
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.replay import refresh,detector_metadata
from piu_timeline.play.tracking import NoteTracker
from piu_timeline.play.observations.cache import detector_replay_available,find_saved_observations,NATIVE_FRAME_FORMAT
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);a=root/'a';b=root/'b';a.mkdir();b.mkdir();items,_=examples(a);examples(b)
 doc=json.loads((b/'bank.json').read_text());doc['annotation']='same measured images';(b/'bank.json').write_text(json.dumps(doc))
 source=root/'source.mkv';source.write_bytes(b'unchanged media')
 media={'path':str(source),'size_bytes':source.stat().st_size,'mtime_ns':source.stat().st_mtime_ns}
 layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1,'color':'blue'}for i in range(5)]};rgb=np.zeros((300,200,3),dtype='uint8');rgb[40:80,10:30]=items[0][1]
 images=SkinDetector(load_bank(a/'bank.json'),layout,200,300).detect(rgb)
 frames=[{'playback_seconds':1.+i*.02,'source_pts_seconds':31.+i*.02,'notes':images,
          'skin_observations':images,'combo':i+4}for i in range(2)]
 trace=''.join(json.dumps(f)+'\n'for f in frames);(root/'frames.jsonl').write_text(trace)
 data={'media':media,'game_roi':[0,0,200,300],'analysis_width':200,'analysis_height':300,'layout':layout,
  'start_seconds':1.,'end_seconds':1.04,'frame_count':2,'native_frame_format':NATIVE_FRAME_FORMAT,
  'skin_detector':detector_metadata(a/'bank.json')}
 with patch('piu_timeline.play.skins.replay.decode_frames',side_effect=AssertionError('unchanged references require no decoding')):
  refresh(data,root,b/'bank.json')
 no_fabricated_backup=not(root/'frames.outline.jsonl').exists()
 preserved=[{k:f[k]for k in ('source_pts_seconds','playback_seconds','combo')}for f in map(json.loads,(root/'frames.jsonl').read_text().splitlines())]
 image_reuse=detector_replay_available(data,root,{'note_skin':str(b/'bank.json')})
 missing_backup=detector_replay_available(data,root,{})
 (root/'frames.outline.jsonl').write_text(trace)
 mislabeled_backup=detector_replay_available(data,root,{})
 outlines=NoteTracker(layout,200,300).detect(rgb)
 genuine=''.join(json.dumps({k:v for k,v in {**f,'notes':outlines}.items()if k!='skin_observations'})+'\n'for f in frames)
 (root/'frames.outline.jsonl').write_text(genuine)
 genuine_available=detector_replay_available(data,root,{})
 with patch('piu_timeline.play.skins.replay.decode_frames',side_effect=AssertionError('no pixel change')):refresh(data,root,b/'bank.json')
 genuine_preserved=(root/'frames.outline.jsonl').read_text()==genuine
 good=root/'segment-001.previous-good';bad=root/'segment-001.previous-bad'
 for folder,backup in [(good,genuine),(bad,trace)]:
  folder.mkdir();(folder/'analysis.json').write_text(json.dumps(data));(folder/'frames.jsonl').write_text(trace);(folder/'frames.outline.jsonl').write_text(backup)
 os.utime(bad/'analysis.json',(2000000000,2000000000))
 document={'media':media,'game_roi':[0,0,200,300]};segment={'chart':'S10'}
 selected=find_saved_observations(root,root/'segment-001',document,segment,1.,1.04,{'width':200})
 print(json.dumps({'no_fabricated_backup':no_fabricated_backup,'preserved':preserved,'image_reuse':image_reuse,
  'missing_backup':missing_backup,'mislabeled_backup':mislabeled_backup,'genuine_available':genuine_available,
  'genuine_preserved':genuine_preserved,'selected':selected[1].name,'source_unchanged':source.read_bytes()==b'unchanged media'}))
`;
const observed=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}).trim().split('\n').at(-1));
test('image-to-image reuse cannot fabricate an original contour acquisition',()=>{
 assert.equal(observed.no_fabricated_backup,true);assert.equal(observed.image_reuse,true);
 assert.deepEqual(observed.preserved,[{source_pts_seconds:31,playback_seconds:1,combo:4},{source_pts_seconds:31.02,playback_seconds:1.02,combo:5}]);
 assert.equal(observed.source_unchanged,true);
});
test('detector reset rejects missing or mislabeled images and preserves genuine outlines',()=>{
 assert.equal(observed.missing_backup,false);assert.equal(observed.mislabeled_backup,false);
 assert.equal(observed.genuine_available,true);assert.equal(observed.genuine_preserved,true);
 assert.equal(observed.selected,'segment-001.previous-good');
});
