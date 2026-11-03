import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

test('evidence relocation preserves numerical bytes, keys and source paths and publishes atomically',()=>{
 const script=String.raw`
import json,tempfile
from pathlib import Path
from unittest.mock import patch
from piu_timeline.storage import relocate_evidence
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);source=root/'old-한글-"-\\';source.mkdir();target=root/'new-한글-"-\\'
 prefix=str(source)+'/'
 original={'nested':[prefix+'image-"-\\.png',{'file':prefix+'nested/frame.png'}],
  'media':str(root/'recording.mp4'),'numbers':[[i/60,1.2300e-12]for i in range(10000)],
  prefix+'key.png':'unchanged key','quoted':'embedded "'+prefix+'not-a-path',
  'sibling':str(source)+'-sibling/frame.png','directory':str(source)}
 for ascii in (True,False):
  path=source/f'analysis-{ascii}.json';text=json.dumps(original,ensure_ascii=ascii,separators=(',',':'))
  # Numerical lexemes/whitespace belong to retained evidence, not relocation.
  text=text.replace('1.23e-12','1.2300e-012');path.write_text(text)
 unchanged=source/'positions.json';unchanged.write_text('[ [1.00,2e-10],  [3,4] ]\n');stamp=unchanged.stat().st_mtime_ns
 relocate_evidence(source,target)
 for ascii in (True,False):
  path=source/f'analysis-{ascii}.json';text=path.read_text();result=json.loads(text)
  expected={**original,'nested':[str(target)+'/'+x[len(prefix):]if isinstance(x,str)else{'file':str(target)+'/nested/frame.png'}for x in original['nested']]}
  assert result==expected
  assert '1.2300e-012'in text and text.count('1.2300e-012')==10000
 assert unchanged.read_text()=='[ [1.00,2e-10],  [3,4] ]\n'and unchanged.stat().st_mtime_ns==stamp
 # Failure to promote a rewritten file cannot truncate the previous artifact.
 failing=source/'failure.json';before=json.dumps({'image':prefix+'frame.png'});failing.write_text(before)
 with patch.object(Path,'replace',side_effect=OSError('simulated interrupted publication')):
  try:relocate_evidence(source,target)
  except OSError:pass
  else:raise AssertionError('publication failure was ignored')
 assert failing.read_text()==before and not list(source.glob('*.relocate-build'))
 print(json.dumps({'verified':True}))
`;
 const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.equal(result.verified,true);
});
