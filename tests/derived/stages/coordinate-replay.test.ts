import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
import {measuredGapScene}from '../fixtures.ts';
const script=String.raw`
import sys,json,tempfile,copy
from pathlib import Path
from unittest.mock import patch
from piu_timeline.play import analysis
from piu_timeline.play.stages import save_coordinates
from piu_timeline.play.observations.cache import NATIVE_FRAME_FORMAT
from piu_timeline.play.coordinate_replay import applicable
scene=json.load(sys.stdin)
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);directory=root/'example';final=directory/'play/segment-001';final.mkdir(parents=True)
 (directory/'analysis').mkdir();video=directory/'source.mkv';video.write_bytes(b'original');stat=video.stat()
 media={'path':str(video),'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns}
 bank={'skin':'generated','sha256':'a'*64};segment={'start_seconds':.2,'end_seconds':1.3,'song':'generated','chart':'S10','players':{}}
 doc={'media':media,'game_roi':[0,0,650,365],'segments':[segment]};(directory/'analysis/analysis.json').write_text(json.dumps(doc))
 for row in scene['head_registration']['notes']:
  for o in row['observations']:o.update(detected_y_pixels=o['native_y_pixels'],native_cap_projection_uncertainty_pixels=1.)
 base={**scene,**segment,'media':media,'game_roi':doc['game_roi'],'skin_detector':{'contract':bank},
       'frame_count':len(scene['scroll_motion']['samples']),'combo_events':[],'unsupported_intervals':[],
       'native_frame_format':NATIVE_FRAME_FORMAT,'play_analysis_version':analysis.VERSION,
       'timing_format':copy.deepcopy(analysis.TIMING_FORMAT),'segment_number':1,'participant_slots':[]}
 base['frame_timeline']=[{'time':s['time'],'source_pts':s['source_pts']}for s in scene['scroll_motion']['samples']]
 base['timing_format']['native_clock'].pop('detector_gaps')
 (final/'frames.jsonl').write_text('raw frames must not be parsed for a clock-only change')
 results=[]
 for stale in [False,True]:
  cached=copy.deepcopy(base)
  if stale:cached['timing_format']['frame_tracking']['revision']+=100
  cached=save_coordinates(cached,final);(final/'analysis.json').write_text(json.dumps(cached))
  captured=[]
  def finish(value,*args,**kwargs):captured.append((value,kwargs));return 'published'
  with (patch.object(analysis,'LOCAL_DATA',root),
        patch.object(analysis,'source_id',return_value='example'),
        patch.object(analysis,'observation_settings_match',return_value=True),
        patch.object(analysis,'objects_current',return_value=True),
        patch.object(analysis,'result_reference',return_value=None),
        patch('piu_timeline.play.skins.replay.selected_bank',return_value='/generated/bank.json'),
        patch('piu_timeline.play.skins.replay.detector_contract',return_value=bank),
        patch.object(analysis,'finish_play',side_effect=finish),
        patch.object(analysis,'refit_saved',side_effect=RuntimeError('raw replay requested')),
        patch.object(analysis,'analyze_play',side_effect=AssertionError('source decoding forbidden')),
        patch('piu_timeline.play.head_registration.measure_coordinates',side_effect=AssertionError('remeasurement forbidden'))):
   try:outcome=analysis.run('example')
   except RuntimeError as error:outcome=str(error)
  if stale:results.append(outcome=='raw replay requested'and not captured)
  else:
   value,options=captured[0]
   results.append(outcome=='published'and options.get('registered_coordinates')is True and value['timing_format']==analysis.TIMING_FORMAT
    and [n['points']for n in value['notes']]==[n['points']for n in scene['notes']]
    and [s['source_pts']for s in value['frame_timeline']]==[s['source_pts']for s in scene['scroll_motion']['samples']])
 print(json.dumps({'clock_only':results[0],'other_producer_requires_replay':results[1],'media_preserved':video.read_bytes()==b'original'}))
`;
test('a native-clock-only change refits bound coordinates; changed observation producers require frame replay',()=>{
 const scene=measuredGapScene(),r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],
  {input:JSON.stringify(scene),encoding:'utf8'}).trim().split('\n').at(-1));
 assert.deepEqual(r,{clock_only:true,other_producer_requires_replay:true,media_preserved:true});
});
