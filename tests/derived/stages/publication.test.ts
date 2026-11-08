/** Stage completion cannot claim a published report; failed promotion retains the prior one. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
const script=String.raw`
import json,tempfile
from pathlib import Path
from unittest.mock import patch
from piu_timeline.play.stages import execute,publish
results=[]
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp)
 for fail in (False,True):
  parent=root/str(fail);parent.mkdir();pending=parent/'segment-001.build-new';pending.mkdir();final=parent/'segment-001';final.mkdir()
  (final/'report.html').write_text('previous report')
  (pending/'analysis.json').write_text('{}')
  execute(pending,'coordinates',lambda:(pending/'coordinates.json').write_text('{}'),('coordinates.json',))
  before=json.loads((pending/'pipeline-status.json').read_text())
  (pending/'report.html').write_text('new report')
  rename=Path.rename
  def promote(path,target):
   if fail and path==pending:raise OSError('injected publication failure')
   return rename(path,target)
  with patch.object(Path,'rename',promote):
   try:publish(pending,final)
   except OSError:pass
  status=json.loads(((pending if fail else final)/'pipeline-status.json').read_text())
  results.append({'between':before['status'],'stage':before['stage_status'],'after':status['status'],'report':(final/'report.html').read_text(),'publication':status['stages']['publication']['status']})
 pending=root/'missing-output';pending.mkdir()
 try:execute(pending,'coordinates',lambda:None,('coordinates.json',))
 except ValueError:pass
 missing=json.loads((pending/'pipeline-status.json').read_text())
 print(json.dumps({'runs':results,'missing_output':missing['status']}))
`;
test('publication status follows successful atomic promotion and records failed output contracts',()=>{
 const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}).trim().split('\n').at(-1));
 assert.deepEqual(result,{runs:[
  {between:'running',stage:'complete',after:'published',report:'new report',publication:'complete'},
  {between:'running',stage:'complete',after:'failed',report:'previous report',publication:'failed'},
 ],missing_output:'failed'});
});
