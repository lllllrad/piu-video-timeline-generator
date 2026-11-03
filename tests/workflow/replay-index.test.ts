import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const script=String.raw`
import json,tempfile,sys,os
from pathlib import Path
from unittest.mock import patch
from piu_timeline.tools.replay import Replay
from piu_timeline.tools import replay
from piu_timeline.play.report import write_index,write_report
with tempfile.TemporaryDirectory()as temporary:
 root=Path(temporary);source=root/'.local/data/example';metadata=source/'analysis';metadata.mkdir(parents=True)
 document={'segments':[{'song':'First song','chart':'S10'},{'song':'Second song','chart':'D12'}]}
 (metadata/'analysis.json').write_text(json.dumps(document))
 play=source/'play';one=play/'segment-001';one.mkdir(parents=True)
 summary={'coverage':{'visible_note_heads':4,'timed_note_heads':3,'matched_combo_updates':2},'combo_readable_fraction':.9,'play_analysis_version':1}
 view={**summary,'media':{'path':str(source/'recording.mp4')},'song':'First song','chart':'S10'}
 write_report(view,one/'report.html')
 (one/'report-data.json').write_text(json.dumps(view))
 native=one/'frames.jsonl';native.write_bytes(b'unchanged native evidence')
 runner=Replay(root,root/'run',acquire=True,jobs=1);before=[]
 def refresh(source,number,*args):
  before.append((play/'index.html').read_text())
  two=play/'segment-002';two.mkdir()
  write_report({**view,'song':'Second song','chart':'D12'},two/'report.html')
  return {'status':'current'}
 with patch('piu_timeline.tools.replay.current',side_effect=lambda path:path.parent.name=='segment-001'),patch.object(runner,'refresh',side_effect=refresh):
  runner.cycle()
 after=(play/'index.html').read_text();(play/'index.html').unlink()
 with patch('piu_timeline.tools.replay.current',return_value=True),patch.object(runner,'refresh',side_effect=AssertionError('no acquisition for current reports')):
  runner.cycle()
 repaired=(play/'index.html').read_text()
 (one/'report-summary.json').unlink()
 write_index(document,play)
 recovered=(play/'index.html').read_text();recovered_summary=json.loads((one/'report-summary.json').read_text())
 changed={**view,'coverage':{**view['coverage'],'visible_note_heads':8}}
 prepared=one/'report-data.json';prepared.write_text(json.dumps(changed))
 newer=(one/'report-summary.json').stat().st_mtime_ns+1000000
 os.utime(prepared,ns=(newer,newer));write_index(document,play)
 refreshed_summary=json.loads((one/'report-summary.json').read_text())
 prepared.write_text(json.dumps(view));write_report(view,one/'report.html');write_index(document,play)
 with patch('piu_timeline.derived.call',side_effect=RuntimeError('render failed')):
  try:write_index(document,play)
  except RuntimeError:pass
 preserved=(play/'index.html').read_text()==repaired;no_pending=not list(play.glob('.index.*.tmp'))
 read=Path.read_text
 def during_promotion(path,*args,**kwargs):
  if path.parent==one and path.name in ('report-summary.json','report-data.json'):raise FileNotFoundError('directory promotion')
  return read(path,*args,**kwargs)
 with patch.object(Path,'read_text',new=during_promotion):write_index(document,play)
 promotion=(play/'index.html').read_text()
 with patch.object(replay,'ROOT',root),patch.object(sys,'argv',['replay','--acquire','--sources','example','--run-dir',str(root/'.local/runs/deferred')]),patch.object(replay,'current',return_value=False),patch.object(Replay,'refresh',return_value={'status':'queued'}):
  try:replay.main();exitcode=None
  except SystemExit as error:exitcode=error.code
 print(json.dumps({'before':before,'after':after,'repaired':repaired,'failed_render_preserved':preserved,
  'deferred_exitcode':exitcode,'deferred_state':json.loads((root/'.local/runs/deferred/progress.json').read_text())['state'],
  'promotion':promotion,
  'recovered':recovered,'recovered_summary':recovered_summary,
  'refreshed_summary':refreshed_summary,
  'no_pending':no_pending,'native_preserved':native.read_bytes()==b'unchanged native evidence'}))
`;
const result=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));

test('parallel replay publishes available reports before acquisition and updates links after each completion',()=>{
 assert.equal(result.before.length,1);
 assert.match(result.before[0],/segment-001\/report.html/);
 assert.doesNotMatch(result.before[0],/segment-002\/report.html/);
 assert.match(result.before[0],/Second song/);assert.match(result.before[0],/Unavailable/);
 assert.match(result.after,/segment-002\/report.html/);assert.equal(result.native_preserved,true);
});
test('replay repairs a missing source index without refreshing current analyses',()=>{
 assert.equal(result.repaired,result.after);
});
test('real report publication produces index summaries and repairs missing summaries from saved views',()=>{
 assert.equal(result.recovered,result.after);
 assert.equal(result.recovered_summary.coverage.visible_note_heads,4);
 assert.equal(result.recovered_summary.play_analysis_version,1);
});
test('a newer prepared view refreshes stale summary counts without inference',()=>{
 assert.equal(result.refreshed_summary.coverage.visible_note_heads,8);
});
test('a failed index render preserves the published file and removes its temporary file',()=>{
 assert.equal(result.failed_render_preserved,true);assert.equal(result.no_pending,true);
});
test('a batch with queued artifacts cannot exit successfully and imply completion',()=>{
 assert.equal(result.deferred_state,'deferred');assert.equal(result.deferred_exitcode,1);
});
test('a summary temporarily absent during parallel promotion remains an unavailable row',()=>{
 assert.match(result.promotion,/First song/);assert.match(result.promotion,/Unavailable/);
 assert.doesNotMatch(result.promotion,/segment-001\/report.html/);
 assert.match(result.promotion,/segment-002\/report.html/);
});
