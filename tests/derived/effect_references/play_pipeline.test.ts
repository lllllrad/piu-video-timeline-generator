import {gunzipSync} from 'node:zlib';
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,statSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {hash} from '../../../src/piu_timeline/derived/effect_references/io.ts';
import {analyze} from '../../../src/piu_timeline/derived/effect_references/play.ts';
import {stages} from '../../../src/piu_timeline/derived/effect_references/model.ts';

test('saved play measurement is reusable while note links change; corrupt RGB is refused',async t=>{
 const root=mkdtempSync(join(tmpdir(),'piu-effect-play-'));t.after(()=>rmSync(root,{recursive:true,force:true}));
 const original=join(root,'recording.bin');writeFileSync(original,'immutable recording identity');
 const identity={size:statSync(original).size,mtime_ns:'123456789123456789'};
 const create=(name:string,count:number,selection:string)=>{
  const dir=join(root,name);mkdirSync(dir);
  const pixels=Buffer.alloc(count*34*47*47*3),mask=Buffer.alloc(count*34*47*47),events=[];
  for(let n=0;n<count;n++) {
   const frames=[];
   for(let i=0;i<34;i++) {
    const offset=n*34+i;pixels.fill(60+i*4,offset*47*47*3,(offset+1)*47*47*3);
    frames.push({offset,pts:100+n*2+i/60,time:n*2+i/60,crop:[0,0,47,47],envelopes:[]});
   }
   events.push({id:`${name}-${n}`,kind:0,lane:0,marker:n*2+8/60,selection_kind:'off_to_on_candidate',frames});
  }
  writeFileSync(join(dir,'pixels.rgb'),pixels);writeFileSync(join(dir,'exclusions.bin'),mask);
  const path=join(dir,'capture.json');writeFileSync(path,JSON.stringify({schema:1,source:original,source_identity:identity,
   segment:join(root,'play/segment-001'),selection,events,pixels_sha256:hash(join(dir,'pixels.rgb')),exclusions_sha256:hash(join(dir,'exclusions.bin'))}));
  return {dir,path,events};
 };
 const training=create('training',3,'sampled_off_to_on'),query=create('query',3,'all_light_candidates');
 const selected=training.events.map(e=>({id:e.id,translation:[0,0],frames:stages.map(dt=>({frame:e.frames[Math.round(8+dt*60)],image_outlier_regions:[]}))}));
 const variant={id:selected[0].id,training_support:3,files:selected[0].frames.map(f=>({frame:f.frame,visible_mask:Array(1521).fill(1)}))};
 const producers=Object.fromEntries(['cli.ts','model.ts','io.ts','bank.ts','regions.ts','temporal.ts'].map(f=>[f,hash(new URL(`../../../src/piu_timeline/derived/effect_references/${f}`,import.meta.url).pathname)]));
 const reference=join(root,'reference.json');writeFileSync(reference,JSON.stringify({schema:2,source:original,source_identity:identity,
  input:training.path,capture_sha256:hash(training.path),implementation_sha256:producers,groups:[{kind:0,accepted:selected,variants:[variant]}]}));
 const request=join(root,'play.json'),notes=[{lane:0,note_type:'tap',target_seconds:.2,visible_start_seconds:0,visible_end_seconds:.4}];
 writeFileSync(request,JSON.stringify({notes,matches:[{note:0,raw_offset_ms:17}],hold_analysis:{holds:[]}}));
 const previous=process.env.PIU_EFFECT_JOBS;process.env.PIU_EFFECT_JOBS='1';
 t.after(()=>{if(previous===undefined)delete process.env.PIU_EFFECT_JOBS;else process.env.PIU_EFFECT_JOBS=previous;});
 const out=join(root,'results'),result=await analyze(reference,query.path,request,out);
 assert.equal(result.counts.candidate_windows,3);assert.equal(result.counts.frame_observations,102);
 const rows=gunzipSync(readFileSync(join(out,'observations.jsonl.gz'))).toString('utf8').trim().split('\n').map(l=>JSON.parse(l));
 assert.equal(rows[0].source_pts_seconds,100);assert.equal(rows.at(-1).source_pts_seconds,104+33/60);
 assert.ok(rows.every(r=>r.origin_pixels.length===2));
 process.env.PIU_EFFECT_JOBS='2';const parallel=join(root,'parallel');
 await analyze(reference,query.path,request,parallel);
 for(const file of ['events.json','observations.jsonl.gz','associations.json'])assert.deepEqual(readFileSync(join(parallel,file)),readFileSync(join(out,file)));
 const before=statSync(join(out,'events.json'),{bigint:true}).mtimeNs;
 notes.push({...notes[0],target_seconds:.21});writeFileSync(request,JSON.stringify({notes,hold_analysis:{holds:[]}}));
 await analyze(reference,query.path,request,out);
 assert.equal(statSync(join(out,'events.json'),{bigint:true}).mtimeNs,before);
 const relations=JSON.parse(readFileSync(join(out,'associations.json'),'utf8'));
 assert.equal(relations.associations[0].physical_input_range,null);
 assert.equal(relations.associations[0].candidates.length,2);
 assert.deepEqual(JSON.parse(readFileSync(request,'utf8')).notes,notes);
 const invalid=JSON.parse(readFileSync(reference,'utf8'));invalid.groups[0].accepted[0].frames[0].frame.pts=999;
 const invalidPath=join(root,'invalid.json');writeFileSync(invalidPath,JSON.stringify(invalid));
 await assert.rejects(()=>analyze(invalidPath,query.path,request,out),/Foreign effect reference frame/);
 writeFileSync(join(query.dir,'pixels.rgb'),'corrupt');
 await assert.rejects(()=>analyze(reference,query.path,request,out),/hash mismatch/);
 assert.equal(readFileSync(original,'utf8'),'immutable recording identity');
});
