/** Large native searches must be consumed once without changing evidence. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
import {imageHoldScene,adjacentImageHolds}from '../fixtures.ts';
const script=String.raw`
import json,sys,tempfile,copy
from pathlib import Path
from unittest.mock import patch
from piu_timeline.play.observations.trace import stream_frames
from piu_timeline.play.skins.holds import measure_connections
from piu_timeline.play.skins.observations import observe
from piu_timeline.play.skins.views import channel_frames
s=json.load(sys.stdin)
# Repeated comparisons model a large search, not additional source objects.
for frame in s['native']:
 for image in frame['skin_observations']:
  positive={**image,'template_role':image['role'],'classification_status':'full_pattern'}
  cap={**image,'role':'unknown','template_role':'tap','classification_status':'cap_only'}
  image['alternatives']=[copy.deepcopy(p)for _ in range(30)for p in (cap,positive)]
  if s['conflicts']:image['conflicting_roles']=[image['role'],'tap']
original=copy.deepcopy(s)
expected_warnings=[]
with patch('piu_timeline.play.skins.views.geometry_frames',side_effect=lambda native,*refs:list(native)):
 expected=measure_connections(s['data'],s['native'],expected_warnings,references=s['references'],cap_references=s['cap_references'])
with tempfile.TemporaryDirectory()as tmp:
 path=Path(tmp)/'frames.jsonl';path.write_text(''.join(json.dumps(f)+'\n'for f in s['native']))
 warnings=[]
 with stream_frames(path,len(s['native']))as native:
  actual=measure_connections(s['data'],native,warnings,references=s['references'],cap_references=s['cap_references'])
 assert actual==expected and warnings==expected_warnings
 with stream_frames(path,len(s['native']))as native:small=channel_frames(native)
 assert observe(s['data'],small)==observe(s['data'],s['native'])
 assert all(len(i['alternatives'])<=2 for f in small for i in f['skin_observations'])
 for count in (len(s['native'])-1,len(s['native'])+1):
  try:
   with stream_frames(path,count)as native:list(native)
  except ValueError:pass
  else:raise AssertionError('Incomplete stream accepted')
 assert json.loads(path.read_text().splitlines()[0])==s['native'][0]
assert s==original
print(json.dumps({'connections':len(actual),'role_proofs_equal':True,'geometry_equal':True}))
`;
for(const scene of [imageHoldScene,adjacentImageHolds])for(const conflicts of [false,true])test(`compact native views preserve ${scene.name}, conflicts=${conflicts}`,()=>{
 const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{input:JSON.stringify({...scene(),conflicts}),encoding:'utf8'}));
 assert.ok(result.geometry_equal);assert.ok(result.role_proofs_equal);
 assert.equal(result.connections,conflicts?0:scene===imageHoldScene?1:2);
});
