import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const script=String.raw`
import json,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from tests.play.skins.test_detector import examples
from piu_timeline.play import analysis
from piu_timeline.play.tracking import NoteTracker
from piu_timeline.play.observations.cache import validate_native_frame
from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.replay import refresh,detector_metadata,configuration_current
def rejected(operation):
 try:operation();return False
 except ValueError:return True
with tempfile.TemporaryDirectory()as temporary:
 root=Path(temporary);source=root/'video.mkv';source.write_bytes(b'original recording')
 media={'path':str(source),'size_bytes':source.stat().st_size,'mtime_ns':source.stat().st_mtime_ns}
 directory=root/'data/example';metadata=directory/'analysis';metadata.mkdir(parents=True)
 (metadata/'analysis.json').write_text(json.dumps({'media':media,'segments':[{'start_seconds':1,'end_seconds':2}]}))
 final=directory/'play/segment-001';final.mkdir(parents=True)
 (final/'report.html').write_text('previous report');(final/'frames.jsonl').write_text('previous evidence')
 with patch.object(analysis,'LOCAL_DATA',root/'data'),patch.object(analysis,'source_id',return_value='example'),patch('piu_timeline.play.skins.replay.selected_bank',return_value=None),patch.object(analysis,'decode_frames',side_effect=AssertionError('no decoding')):
  missing=rejected(lambda:analysis.run('example'))
  fresh=rejected(lambda:analysis.analyze_play({}, {},root/'build'))
 intact=(final/'report.html').read_text()=='previous report'and(final/'frames.jsonl').read_text()=='previous evidence'and not(root/'build').exists()
 layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1,'color':'blue'}for i in range(5)]}
 no_detector=rejected(lambda:NoteTracker(layout,200,300).detect(np.zeros((300,200,3),dtype='uint8')))
 a=root/'a';a.mkdir();items,_=examples(a);bank=load_bank(a/'bank.json')
 rgb=np.zeros((300,200,3),dtype='uint8');rgb[40:80,10:30]=items[0][1]
 notes=NoteTracker(layout,200,300,bank).detect(rgb)
 frame={'source_pts_seconds':31,'playback_seconds':1,'notes':notes,'skin_observations':notes,'combo':4}
 validate_native_frame(frame,5)
 contour={**frame,'notes':[{'lane':0,'x':.1,'y':.2,'method':'colored_head_outline'}]}
 rejected_contours=rejected(lambda:validate_native_frame(contour,5))
 (root/'frames.jsonl').write_text(json.dumps(frame)+'\n')
 cached={'media':media,'game_roi':[0,0,200,300],'analysis_width':200,'analysis_height':300,'layout':layout,
  'start_seconds':1,'end_seconds':1.02,'frame_count':1,'skin_detector':detector_metadata(a/'bank.json')}
 with patch('piu_timeline.play.skins.replay.decode_frames',side_effect=AssertionError('unchanged image references')):
  refresh(cached,root,a/'bank.json')
 updated=json.loads((root/'frames.jsonl').read_text())
 no_backup=not(root/'frames.outline.jsonl').exists()
 (root/'frames.outline.jsonl').write_text(json.dumps(contour)+'\n')
 print(json.dumps({'missing':missing,'fresh':fresh,'intact':intact,'no_detector':no_detector,'notes':len(notes),
  'image_methods':all(n['method']=='skin_image'for n in notes),'rejected_contours':rejected_contours,'no_backup':no_backup,
  'current_without_selection':configuration_current(cached,root,1),
  'counter_preserved':all(updated[k]==frame[k]for k in ('source_pts_seconds','playback_seconds','combo')),
  'source_preserved':source.read_bytes()==b'original recording'}))
`;
const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}).trim().split('\n').at(-1));
test('missing image selection fails before decoding, OCR or modifying an existing report',()=>{
 assert.equal(result.missing,true);assert.equal(result.fresh,true);assert.equal(result.intact,true);
 assert.equal(result.no_detector,true);assert.equal(result.source_preserved,true);
});
test('native acquisition and replay accept image observations and reject contour coordinates',()=>{
 assert.ok(result.notes>0);assert.equal(result.image_methods,true);assert.equal(result.rejected_contours,true);
 assert.equal(result.current_without_selection,false);
 assert.equal(result.counter_preserved,true);assert.equal(result.no_backup,true);
});
