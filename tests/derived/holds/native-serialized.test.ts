import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync}from 'node:child_process';
const script=String.raw`
import json,tempfile
from pathlib import Path
from piu_timeline.play.observations.serialized import reuse
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);(root/'native-stages').mkdir();source=root/'upstream.json';source.write_text('{"value":3}')
 calls=[];output=root/'native-stages/example.json'
 def compute():
  calls.append(1);value=json.loads(source.read_text());output.write_text(json.dumps({'schema':1,'stage':'example','output':value}));return value
 args=(root,'example',('upstream.json',),{}, {'pixels':'unchanged-producer'})
 first=reuse(*args,compute);stamp=output.stat().st_mtime_ns
 def forbidden():raise AssertionError('Do not assemble another request on a cache hit')
 second=reuse(*args,forbidden);unchanged=stamp==output.stat().st_mtime_ns
 source.write_text('{"value":4}');third=reuse(*args,compute)
 output.write_text('{"schema":1,"stage":"example","output":{"value":5}}')
 try:reuse(*args,forbidden);bad=False
 except ValueError:bad=True
 print(json.dumps({'first':first,'second':second,'third':third,'unchanged':unchanged,'calls':len(calls),'corruption':bad}))
`;
test('native stages reuse their serialized producer artifact before building the measurement request',()=>{
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.deepEqual(r,{first:{value:3},second:{value:3},third:{value:4},unchanged:true,calls:2,corruption:true});
});
