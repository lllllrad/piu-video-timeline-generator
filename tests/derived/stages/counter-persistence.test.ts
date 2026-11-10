/** Counter refinement must use the same JSON request for execution and persistence. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
const script=String.raw`
import json,tempfile,copy
from pathlib import Path
from piu_timeline.play.tracking import ComboTracker
from piu_timeline.play.associations import associate_counters
from piu_timeline.derived import call
from piu_timeline.play.stages import read_view
counter=ComboTracker()
for t,value in [(0,5),(.017,5),(.033,5),(.116,6),(.149,7),(.166,7),(.25,7),(.267,8),(.284,8)]:
 counter.update(t,value,.99,'independent_template',40+t)
notes=[{'lane':i,'status':'estimated','target_seconds':target,'prediction_uncertainty_seconds':.005}for i,target in enumerate([.1,.14,.26])]
data={'notes':notes,'unsupported_intervals':[]};original=copy.deepcopy(data)
with tempfile.TemporaryDirectory()as tmp:
 directory=Path(tmp);result=associate_counters(data,counter,0,directory)
 request=json.loads((directory/'counter-input.json').read_text())
 artifact=read_view({'path':str(directory/'counter-associations.json')},directory)
 replay=call('stageAssociations.counters',request,str(directory.resolve())+'/')
 assert all(isinstance(v,list)and v==sorted(set(v))for v in request['constraints'].values())
 assert request['constraints'] and len(request['events'])==3
 assert data==original
 print(json.dumps({'replay':replay==artifact,'matches':[m['note']for m in result['matches']],
 'same_output':artifact['data']['matches']==result['matches'],'events':[(e['before'],e['after'])for e in request['events']]}))
`;
test('a refined counter burst persists replayable candidate arrays and preserves an unrelated row',()=>{
 const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.deepEqual(result,{replay:true,matches:[0,1,2],same_output:true,events:[[5,6],[6,7],[7,8]]});
});
