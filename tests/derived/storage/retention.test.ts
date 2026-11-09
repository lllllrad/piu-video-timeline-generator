import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,readdirSync,renameSync,existsSync,symlinkSync,rmSync,utimesSync,statSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import {prune} from '../../../src/piu_timeline/derived/retention.ts';

const frames='{"source_pts_seconds":71.125,"playback_seconds":1.125,"notes":[],"combo":4}\n';
function snapshot(path:string,version:number,play=true):void {
  mkdirSync(path,{recursive:true});
  writeFileSync(join(path,'analysis.json'),JSON.stringify({version,media:{path:'original.mkv'}}));
  if(play)for(const name of ['frames.jsonl','frames.base.jsonl','report.html'])writeFileSync(join(path,name),frames);
}
function workspace(t):string {
  const path=mkdtempSync(join(tmpdir(),'piu-retention-'));
  t.after(()=>rmSync(path,{recursive:true,force:true}));return path;
}

test('repeated publication retains current native evidence and removes all superseded snapshots',t=>{
  const root=workspace(t),final=join(root,'segment-001'),media=join(root,'original.mkv');
  writeFileSync(media,'original media');snapshot(final,0);
  const rawTimestamp=new Date(100000);utimesSync(media,rawTimestamp,rawTimestamp);
  snapshot(join(root,'segment-002.build-00000001'),2);
  for(let version=1;version<=4;version++) {
    const previous=join(root,`segment-001.previous-${String(version).padStart(8,'0')}`);
    renameSync(final,previous);snapshot(final,version);
    const abandoned=join(root,`segment-001.build-${String(version).padStart(8,'0')}`);
    snapshot(abandoned,version-1);
    const result=prune(final,previous,[media]);
    assert.deepEqual(result.kept,[]);
    assert.equal(existsSync(abandoned),false);
    assert.equal(readdirSync(root).filter(name=>name.startsWith('segment-001.previous-')).length,0);
    assert.equal(existsSync(previous),false);
    assert.equal(readFileSync(join(final,'frames.base.jsonl'),'utf8'),frames);
  }
  assert.equal(existsSync(join(root,'segment-002.build-00000001')),true);
  assert.equal(readFileSync(media,'utf8'),'original media');
  assert.equal(statSync(media).mtimeMs,rawTimestamp.getTime());
});

test('incomplete current evidence preserves histories, baselines and failed attempts',t=>{
  const root=workspace(t),final=join(root,'segment-001'),old=join(root,'segment-001.previous-00000001');
  snapshot(final,2);snapshot(old,1);snapshot(join(root,'segment-001.build-00000001'),3);
  rmSync(join(final,'frames.base.jsonl'));
  const result=prune(final);
  assert.ok(result.reason);assert.deepEqual(result.removed,[]);
  assert.equal(existsSync(old),true);
  assert.equal(existsSync(join(root,'segment-001.build-00000001')),true);
  writeFileSync(join(final,'frames.base.jsonl'),frames);
  writeFileSync(join(final,'analysis.json'),'{truncated');
  assert.deepEqual(prune(final).removed,[]);
  assert.equal(existsSync(old),true);
});

test('native manifest validation is bound to the exact file before history deletion',t=>{
 const root=workspace(t),final=join(root,'segment-001'),old=join(root,'segment-001.previous-00000001');
 snapshot(final,1);snapshot(old,0);
 const path=join(final,'analysis.json'),stat=statSync(path,{bigint:true}),validated={size_bytes:stat.size,mtime_ns:stat.mtimeNs};
 writeFileSync(path,'{"changed":true}');
 assert.throws(()=>prune(final,old,[],validated),/manifest changed/);
 assert.equal(existsSync(old),true);
 const fresh=statSync(path,{bigint:true});
 assert.deepEqual(prune(final,old,[],{size_bytes:fresh.size,mtime_ns:fresh.mtimeNs}).removed,[old]);
});

test('native JSON validation lets a bounded-heap retention worker inspect large saved analyses',()=>{
 const script=String.raw`
import json,tempfile,os
from pathlib import Path
from piu_timeline.storage import prune_history
os.environ['NODE_OPTIONS']='--max-old-space-size=64'
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp);final=root/'segment-001';final.mkdir()
 for name in ('frames.jsonl','frames.base.jsonl','report.html'):(final/name).write_text('{}')
 with (final/'analysis.json').open('w')as stream:
  stream.write('{"padding":"')
  for i in range(64):stream.write('a'*1024*1024)
  stream.write('"}')
 old=root/'segment-001.previous-00000001';old.mkdir();(old/'analysis.json').write_text('{}')
 result=prune_history(final)
 print(json.dumps({'removed':len(result['removed']),'current':final.exists(),'old':old.exists()}))
`;
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.deepEqual(r,{removed:1,current:true,old:false});
});

test('successful publication removes superseded snapshots including malformed results',t=>{
  const root=workspace(t),final=join(root,'analysis');snapshot(final,3,false);
  const good=join(root,'analysis.previous-00000001'),broken=join(root,'analysis.previous-00000002');
  snapshot(good,1,false);snapshot(broken,2,false);writeFileSync(join(broken,'analysis.json'),'{truncated');
  const result=prune(final,broken);
  assert.deepEqual(result.kept,[]);assert.equal(existsSync(good),false);assert.equal(existsSync(broken),false);

});

test('metadata history uses the same policy and protects original media even through a symlink',t=>{
  const root=workspace(t),final=join(root,'analysis');snapshot(final,3,false);
  const older=join(root,'analysis.previous-00000001'),newer=join(root,'analysis.previous-00000002');
  snapshot(older,1,false);snapshot(newer,2,false);
  writeFileSync(join(older,'original.mkv'),'irreplaceable source');
  const media=join(root,'media-link.mkv');symlinkSync(join(older,'original.mkv'),media);
  const result=prune(final,newer,[media]);
  assert.deepEqual(new Set(result.kept),new Set([older]));
  assert.equal(readFileSync(media,'utf8'),'irreplaceable source');
});

test('retention ignores symlink snapshots, human directories and neighboring segment builds',t=>{
  const root=workspace(t),final=join(root,'analysis'),external=join(root,'external');snapshot(final,1,false);
  snapshot(external,42,false);symlinkSync(external,join(root,'analysis.previous-00000001'));
  snapshot(join(root,'analysis.previous-review-notes'),9,false);
  snapshot(join(root,'segment-001.build-00000001'),5);
  assert.deepEqual(prune(final).removed,[]);
  assert.equal(existsSync(join(external,'analysis.json')),true);
  assert.throws(()=>prune(final,external),/sibling snapshot/);
  assert.throws(()=>prune(join(root,'raw')),/canonical analysis/);
});

const adapterScript=String.raw`
import json,subprocess,sys,tempfile,time,shutil,os
from pathlib import Path
from unittest.mock import patch
from piu_timeline.storage import history_guard
from piu_timeline import workflow
with tempfile.TemporaryDirectory()as temporary:
 root=Path(temporary);final=root/'segment-001';final.mkdir()
 for name in ('analysis.json','frames.jsonl','frames.base.jsonl','report.html'):(final/name).write_text('{}\n')
 for number in (1,2):
  previous=root/f'segment-001.previous-{number:08}';previous.mkdir()
  (previous/'analysis.json').write_text(json.dumps({'version':number}))
  (previous/'frames.jsonl').write_text(str(number))
  os.utime(previous/'analysis.json',(number,number))
 old=root/'segment-001.previous-00000001';latest=root/'segment-001.previous-00000002'
 # A copier pins the history before a different process starts pruning it.
 request=root/'requested';copied=root/'segment-002.build-00000001'
 script='from pathlib import Path; from piu_timeline.storage import prune_history; import sys; Path(sys.argv[2]).write_text("ready"); prune_history(Path(sys.argv[1]))'
 with history_guard(root,shared=True):
  process=subprocess.Popen([sys.executable,'-c',script,str(final),str(request)])
  deadline=time.monotonic()+10
  while not request.exists()and time.monotonic()<deadline:time.sleep(.01)
  assert request.exists()and process.poll()is None
  shutil.copytree(old,copied)
 assert process.wait(timeout=20)==0
 pinned=copied.joinpath('frames.jsonl').read_text()=='1'and not old.exists()and not latest.exists()
 statuses=[]
 for fail in (False,True):
  data=root/('failure'if fail else'success');source=data/'synthetic';current=source/'analysis';current.mkdir(parents=True)
  (current/'analysis.json').write_text(json.dumps({'analysis_version':0}))
  prior=source/'analysis.previous-00000001';prior.mkdir();(prior/'analysis.json').write_text('{}')
  abandoned=source/'analysis.build-00000001';abandoned.mkdir();(abandoned/'partial').write_text('diagnostic')
  raw=source/'raw';raw.mkdir();media=raw/'original.mkv';media.write_bytes(b'original recording')
  def acquire(video,target,*args,**kwargs):
   target.mkdir()
   if fail:raise ValueError('acquisition failed')
   (target/'analysis.json').write_text(json.dumps({'analysis_version':workflow.ANALYSIS_VERSION,
    'method':'automatic_hud_ocr','segments':[],'media':{'path':str(media)}}))
  with patch.object(workflow,'LOCAL_DATA',data),patch.object(workflow,'source_id',return_value='synthetic'), \
       patch.object(workflow,'formatter',return_value=Path('unused.ts')),patch.object(workflow,'analyze',side_effect=acquire), \
       patch.object(workflow,'resolve_source',return_value=(media,{'kind':'cached'})), \
       patch.object(workflow,'run_formatter',return_value='timeline\n'),patch('piu_timeline.metadata.badge_recovery.refresh',return_value=False):
   try:workflow.run('synthetic')
   except ValueError:
    if not fail:raise
  statuses.append({'failed':fail,'old_exists':prior.exists(),'build_exists':abandoned.exists(),
   'backups':len(list(source.glob('analysis.previous-*'))),'media':media.read_bytes().decode(),
   'version':json.loads((current/'analysis.json').read_text())['analysis_version']})
 print('RETENTION_RESULT '+json.dumps({'pinned':pinned,'statuses':statuses,'version':workflow.ANALYSIS_VERSION}))
`;
test('native adapters pin copied observations and prune metadata only after a successful atomic publication',()=>{
  const stdout=execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',adapterScript],{encoding:'utf8'});
  const result=JSON.parse(stdout.split('\n').find(line=>line.startsWith('RETENTION_RESULT ')).slice('RETENTION_RESULT '.length));
  assert.equal(result.pinned,true);
  assert.deepEqual(result.statuses,[
    {failed:false,old_exists:false,build_exists:false,backups:0,media:'original recording',version:result.version},
    {failed:true,old_exists:true,build_exists:true,backups:1,media:'original recording',version:0},
  ]);
});
