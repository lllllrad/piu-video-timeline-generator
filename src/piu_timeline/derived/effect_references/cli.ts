/** Saved-RGB reference extraction: node .../cli.ts CAPTURE_JSON NEW_OUTPUT_DIR. */
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {aggregate,align,compare,disjoint,median,policy,reason,sequence,stages,changeCandidates} from './model.ts';
import {accepted as eligible,variants,recognize} from './bank.ts';
import {stringifyData} from '../json.ts';
import {load,png,hash} from './io.ts';
import type {Fit,Patch} from './model.ts';

export function run(input:string,output:string) {
  const root=resolve(fileURLToPath(new URL('../../../../',import.meta.url)),'.local');
  output=resolve(output);
  if(!output.startsWith(root+sep))throw new Error('Output must be a new directory under project .local');
  const {capture,manifest}=load(input);
  mkdirSync(output,{recursive:false});
  const groups=[];
  for(let kind=0;kind<5;kind++) {
    const events=capture.events.filter(e=>e.kind===kind).sort((a,b)=>a.marker-b.marker);
    const train=events.filter((_,i)=>i%3!==2),test=events.filter((_,i)=>i%3===2);
    const candidates=train.map(event=>({event,patches:sequence(capture,event)}))
      .filter(s=>s.patches.filter(p=>p&&!reason(p)).length>=policy.minStages);
    // Medoid choice uses training images alone; held-out frames cannot influence it.
    const ranked=candidates.map(seed=>({seed,score:median(train.filter(e=>e!==seed.event)
      .map(e=>{const es=sequence(capture,e).map((p,i)=>compare(p,seed.patches[i])).filter(x=>x!==null);return es.length>=policy.minStages?median(es):null;}).filter(e=>e!=null))??Infinity})).sort((a,b)=>a.score-b.score);
    if(!ranked.length) {
      groups.push({kind,status:'no_clean_seed',excluded:events.map(e=>({id:e.id,reason:'insufficient_unoccluded_or_unsaturated_stages'}))});continue;
    }
    const seed=ranked[0].seed,accepted:{id:string;fit:Fit}[]=[],excluded=[];
    for(const e of train) {
      const fit=align(capture,e,seed.patches);
      if(!eligible(fit))excluded.push({id:e.id,reason:!fit?'insufficient_visible_stages':fit.rawError>policy.maxRawError?'large_raw_RGB_alignment_error':'large_RGB_alignment_error',error:fit?.error??null,raw_error:fit?.rawError??null});
      else accepted.push({id:e.id,fit});
    }
    for(const rejected of excluded) {
      const event=train.find(e=>e.id===rejected.id);
      const p=sequence(capture,event)[0];
      if(p) {
        const file=`rejected-kind-${kind}-${train.indexOf(event)}.png`;png(resolve(output,file),p);
        Object.assign(rejected,{preview:file,frame:p.frame,stage_reasons:sequence(capture,event).map(p=>p?reason(p):'missing_native_stage')});
      }
    }
    const files=[];
    for(let stage=0;stage<stages.length;stage++) {
      const p=aggregate(accepted.map(c=>c.fit.patches[stage]));
      const failure=reason(p);
      if(failure){files.push({stage,status:'insufficient_consensus',reason:failure});continue;}
      const name=`kind-${kind}-stage-${stage}.png`;
      png(resolve(output,name),p);
      const contributors=accepted.map(a=>({id:a.id,patch:a.fit.patches[stage]})).filter(a=>a.patch&&!reason(a.patch));
      const representative=contributors.map(a=>({...a,error:compare(a.patch,p)})).filter(a=>a.error!==null&&a.error<=policy.maxError).sort((a,b)=>a.error-b.error)[0];
      let actual=null;
      if(representative) {
        const file=`kind-${kind}-stage-${stage}-actual.png`;png(resolve(output,file),representative.patch);
        actual={file,sha256:hash(resolve(output,file)),event:representative.id,frame:representative.patch.frame};
      }
      files.push({stage,status:'candidate_reference',file:name,sha256:hash(resolve(output,name)),actual,
        visible_fraction:p.visible.reduce((a,b)=>a+b,0)/(39*39),pixel_contributor_counts:Array.from(p.contributors),
        visible_mask:Array.from(p.visible)});
    }
    const consensus:Patch[]=stages.map((_,i)=>aggregate(accepted.map(a=>a.fit.patches[i])));
    const actualVariants=variants(accepted.map(a=>({id:a.id,patches:a.fit.patches})));
    const variantFiles=actualVariants.map((v,index)=>({id:v.id,training_support:v.support,files:v.patches.map((p,stage)=>{
      if(!p)return null;const file=`kind-${kind}-variant-${index}-stage-${stage}.png`;png(resolve(output,file),p);
      return {file,sha256:hash(resolve(output,file)),frame:p.frame,visible_mask:Array.from(p.visible)};
    })}));
    const references=[{id:'consensus',patches:consensus},...actualVariants];
    const validation=test.map(e=>{
      if(!train.every(t=>disjoint(e,t)))return {id:e.id,status:'training_frame_overlap'};
      const recognition=recognize(capture,e,references),fit=recognition.best?.fit;
      return {id:e.id,status:recognition.status,error:fit?.error??null,raw_error:fit?.rawError??null,
        offset:fit?.offset??null,alternatives:fit?.alternatives??[],reference:recognition.best?.reference,
        transition:fit?.transition,order_margin:recognition.order_margin,reverse_score:recognition.reverse_score,
        constant_score:recognition.constant_score,reference_alternatives:recognition.alternatives,
        image_change_candidates:changeCandidates(capture,e),
        frames:fit?.patches.map(p=>({source:p?.frame??null,image_outlier_regions:p?.imageOutliers??[]}))};
    });
    groups.push({kind,status:files.some(f=>f.status==='candidate_reference')?'candidate_bank':'insufficient_consensus',
      seed:seed.event.id,variants:variantFiles,accepted:accepted.map(a=>({id:a.id,error:a.fit.error,raw_error:a.fit.rawError,transition:a.fit.transition,offset:a.fit.offset,translation:[a.fit.dx,a.fit.dy],
        alternatives:a.fit.alternatives,frames:a.fit.patches.map(p=>({frame:p?.frame??null,image_outlier_regions:p?.imageOutliers??[],exclusion:p?reason(p):'missing_native_stage'}))})),
      excluded,files,validation});
  }
  const implementation_sha256=Object.fromEntries(['cli.ts','model.ts','io.ts','bank.ts','regions.ts','temporal.ts'].map(name=>[name,hash(fileURLToPath(new URL(name,import.meta.url)))]));
  const result={schema:2,implementation_sha256,input:resolve(input),capture_sha256:hash(input),source:manifest.source,source_identity:manifest.source_identity,
    policy,stages,groups,limits:[
      'Experimental candidate images; no effect-onset or physical-input calibration; not automatically published to the production analyzer.',
      'Source bindings do not certify a named skin. Banks from different captures remain separate.',
      'Note/body envelopes are conservative approximate exclusions, not verified opacity or layer order. Occlusion alone never excludes an entire event if enough visible stages remain.',
      'Thresholds are configurable code policy, not calibrated probabilities. Saturated frames cannot establish distinct phases.',
      'Consensus is synthetic median imagery; actual representatives retain source PTS and crop. Checkerboard means unsupported pixels, not inferred artwork.',
      'Residual-based image outlier regions are possible contamination, not independently proven occlusion; at most 20% extra support is excluded. Raw RGB residual remains gated.',
      'Image-change brackets are candidate alignment anchors, not certified effect onsets. Ordered matches need transition evidence and a margin against reversed/constant sequences.',
      'Alignment ambiguity is retained. Stage labels are relative to a source marker, never button ages.']};
  writeFileSync(resolve(output,'results.json'),stringifyData(result)+'\n');
  const escape=(v:unknown)=>String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
  let html='<!doctype html><meta charset="utf-8"><title>Effect reference extraction</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;background:#171b20;color:#eee}a{color:#9cf}img{width:117px;image-rendering:pixelated}td{padding:6px}</style><h1>RGB effect reference candidates</h1><p><a href="results.json">Decisions, rejected observations, masks, alternatives and provenance</a></p>';
  html+='<ul>'+result.limits.map(s=>'<li>'+escape(s)+'</li>').join('')+'</ul>';
  for(const group of groups) {
    html+=`<h2>Direction ${group.kind}: ${group.status}</h2>`;
    if(!group.files){html+=`<p>Excluded ${group.excluded.length} windows; no clean seed.</p>`;continue;}
    html+=`<p>${group.accepted.length} accepted training windows; ${group.excluded.length} excluded. Consensus / actual representative:</p><table>`;
    for(const f of group.files)html+=`<tr><td>Stage ${f.stage}</td><td>${f.file?`<img src="${f.file}">`:escape(f.reason)}</td><td>${f.actual?`<img src="${f.actual.file}">`:''}</td></tr>`;
    html+='</table><h3>Excluded training windows</h3><table>'+group.excluded.map(e=>`<tr><td>${escape(e.id)}: ${escape(e.reason)} (${e.error??'no fit'})</td><td>${e.preview?`<img src="${e.preview}">`:''}</td></tr>`).join('')+'</table>';
    html+='<h3>Training-only actual RGB variants</h3>';
    for(const variant of group.variants)html+='<p>'+escape(variant.id)+'; support '+variant.training_support+'</p>'+variant.files.filter(Boolean).map(f=>`<img src="${f.file}">`).join('');
    html+='<h3>Validation: appearance and phase are separate</h3><table><tr><th>Case</th><th>Status</th><th>RGB / raw</th><th>Offset</th><th>Order margin</th></tr>'+group.validation.map(v=>`<tr><td>${escape(v.id)}</td><td>${escape(v.status)}</td><td>${v.error?.toFixed(3)??'—'} / ${v.raw_error?.toFixed(3)??'—'}</td><td>${v.offset?.toFixed(3)??'—'}</td><td>${v.order_margin?.toFixed(3)??'—'}</td></tr>`).join('')+'</table>';
  }
  writeFileSync(resolve(output,'report.html'),html);
  return result;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  if(process.argv.length!==4)throw new Error('Usage: cli.ts CAPTURE_JSON NEW_OUTPUT_DIR');
  const result=run(process.argv[2],process.argv[3]);console.log(JSON.stringify(result.groups.map(g=>({kind:g.kind,status:g.status,accepted:g.accepted?.length??0,excluded:g.excluded?.length??0}))));
}
