/** Native consumers must replay complete observations without retaining whole traces. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
const script=String.raw`
import json,tempfile
from pathlib import Path
from piu_timeline.play.observations.trace import FrameTrace,stream_frames
from piu_timeline.play.object_roles import filter_frames
records=[{'playback_seconds':i/60,'source_pts_seconds':40+i/60,'notes':[{'lane':0,'x':.1,'y':.4}],
 'skin_observations':[{'role':'hold_start','alternatives':[{'role':'tap','pixels':list(range(1000))}]}],
 'possible_hold_or_dense_stack':False,'combo':i}for i in range(4)]
with tempfile.TemporaryDirectory()as tmp:
 path=Path(tmp)/'frames.jsonl';path.write_text(''.join(json.dumps(r)+'\n'for r in records))
 with stream_frames(path,4)as frames:assert list(frames)==records
 for count in (3,5):
  try:
   with stream_frames(path,count)as frames:list(frames)
  except ValueError:pass
  else:raise AssertionError('Incomplete stream accepted')
 with FrameTrace(path,4)as trace:
  assert len(trace)==4
  assert all(not isinstance(v,(dict,list))for f in trace for v in f.scalars.values())
  assert [dict(f)for f in trace]==records
  first=trace[0]['skin_observations'];assert first==records[0]['skin_observations']
  trace[3]['skin_observations'];assert trace.cached_offset==trace[3].offset
  assert trace[0]['skin_observations']==first
  effect={'id':'skip','chart_processing':'skip_non_playable_interval','game_image_bounds':[0,0,1,1],
   'playback_start_seconds':0,'playback_end_seconds':1,'boundary_uncertainty_seconds':0}
  data={'object_interpretation':{'effects':[effect]}}
  views=filter_frames(data,trace)
  assert all(v['notes']==[]and v['skin_observations']==[]for v in views)
  assert [dict(f)for f in trace]==records
  assert [dict(f)for f in filter_frames(data,records)]==[dict(f)for f in views]
 try:trace[0]['skin_observations']
 except ValueError:pass
 else:raise AssertionError('Closed trace accepted')
 try:
  with FrameTrace(path,5):pass
 except ValueError:pass
 else:raise AssertionError('Incomplete indexed trace accepted')
print('ok')
`;
test('streamed and replayable native frames preserve fields, counts and decorative overlays',()=>{
 assert.equal(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}).trim(),'ok');
});
