import test from 'node:test';
import assert from 'node:assert/strict';
import{execFileSync}from'node:child_process';
const script=String.raw`
import json,tempfile
from pathlib import Path
from piu_timeline.play.observations.warnings import presentation_source
with tempfile.TemporaryDirectory()as tmp:
 root=Path(tmp)
 warning={'reason':'ambiguous_note_tracking','check':'note_visibility',
  'visible_start_seconds':1,'visible_end_seconds':1,'source_pts_seconds':[81],
  'observed_points':2,'candidate_edges':[{'lane':0,'label':'한글🙂'}],
  'candidate_frame_displacements':[{'lower':2,'upper':2}]}
 data={'notes':[{'lane':i,'tracking_warnings':[warning]}for i in range(3)]}
 before=json.dumps(data);view=presentation_source(data,root)
 files=list((root/'evidence'/'tracking-warnings').glob('*.json'))
 proof=json.loads(files[0].read_text());again=presentation_source(data,root)
 files[0].write_text('{}')
 try:presentation_source(data,root);corrupt=False
 except ValueError:corrupt=True
 print(json.dumps({'view':view,'original':data,'unchanged':before==json.dumps(data),
  'files':len(files),'proof':proof,'repeat':again==view,'corrupt_rejected':corrupt}))
`;
test('repeated tracking proofs keep every warning, original fields and one verifiable sidecar',()=>{
 const r=JSON.parse(execFileSync('sh',['scripts/run.sh','.venv/bin/python','-c',script],{encoding:'utf8'}));
 assert.equal(r.unchanged,true);assert.equal(r.files,1);assert.equal(r.repeat,true);assert.equal(r.corrupt_rejected,true);
 assert.equal(r.view.notes.length,3);
 const paths=new Set();
 for(const [i,note]of r.view.notes.entries()){
  assert.equal(note.tracking_warnings.length,1);
  const {tracking_evidence,...warning}=note.tracking_warnings[0];
  paths.add(tracking_evidence.path);
  assert.equal(tracking_evidence.path,`evidence/tracking-warnings/${tracking_evidence.sha256}.json`);
  const original=r.original.notes[i].tracking_warnings[0];
  assert.deepEqual({...warning,candidate_edges:r.proof.candidate_edges,
   candidate_frame_displacements:r.proof.candidate_frame_displacements},original);
  assert.deepEqual(r.proof,original);
 }
 assert.equal(paths.size,1);
});
