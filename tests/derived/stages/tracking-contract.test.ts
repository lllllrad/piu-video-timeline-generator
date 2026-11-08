/** Exercise the native tracking adapter with generated positions, without media or OCR. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
const script=String.raw`
import json,tempfile
from pathlib import Path
from unittest.mock import patch
from piu_timeline import derived
from piu_timeline.play.tracking import NoteTracker,Track,ComboTracker,collect_tracks
layout={'receptor_y':.1,'note_y_max':.95,'lanes':[{'x':.1+.1*i}for i in range(5)]}
results=[]
for certified in (True,False):
 tracker=NoteTracker(layout,400,400)
 times=[i/60 for i in range(61)];tracker.timeline=[{'time':t,'source_pts':100+t}for t in times]
 for lane,selected,shift,reference in [(0,[t for t in times if .1<=t<=.4],30,'a'),(0,[t for t in times if .6<=t<=.9],-20,'b'),(1,times,0,'peer1'),(2,times,0,'peer2')]:
  points=[(t,300+lane*15-120*t+shift)for t in selected]
  records=[{'time':t,'sourcePtsSeconds':100+t,
   'anchor':{'yPixels':y,'uncertaintyPixels':.5,'basis':{'kind':'image_reference_anchor','reference':{'kind':'sha256','value':reference}}},
   'center':{'yPixels':y-shift,'uncertaintyPixels':.5,'basis':{'kind':'native_cap_center'}}if certified or lane else None}for t,y in points]
  tracker.finished.append(Track(lane,points,coordinate_points=records))
 calls=[];original=derived.call
 def guarded(operation,*args,**kwargs):
  calls.append(operation)
  if operation.startswith(('clocks.','nativeClock.','physicalTiming.','stageAssociations.')):raise AssertionError('Tracking requested a timing/input calculation')
  return original(operation,*args,**kwargs)
 with tempfile.TemporaryDirectory()as tmp,patch.object(derived,'call',side_effect=guarded):
  directory=Path(tmp);result=collect_tracks(tracker,ComboTracker(),directory,{'media':{'path':'generated'},'start_seconds':0,'end_seconds':1})
  artifact=json.loads((directory/'tracking.json').read_text())
  caps=[n for n in result['notes']if n['lane']==0]
  results.append({'caps':len(caps),'no_times':all('target_seconds'not in n and 'status'not in n for n in result['notes']),
   'raw_preserved':sorted(p for n in caps for p in n['points'])==sorted(list(p)for t in tracker.finished if t.lane==0 for p in t.points),
   'source_bound':bool(artifact['input_fingerprint']),'clock_calls':any(op.startswith('clocks.')for op in calls)})
print(json.dumps(results))
`;
test('tracking stores visual identities, preserves raw anchors and refuses incomparable fragment origins',()=>{
 const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.deepEqual(result,[
  {caps:1,no_times:true,raw_preserved:true,source_bound:true,clock_calls:false},
  {caps:2,no_times:true,raw_preserved:true,source_bound:true,clock_calls:false},
 ]);
});
