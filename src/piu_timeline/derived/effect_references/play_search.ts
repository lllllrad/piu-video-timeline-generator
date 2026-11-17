/** Coarse RGB proposals, then full-resolution validation for bounded play cost. */
import {sequence,compare,reason,policy} from './model.ts';
import {regions} from './regions.ts';
import {evolution} from './temporal.ts';
import {accepted} from './bank.ts';
export const SEARCH={method:'sampled_RGB_proposals_full_RGB_validation',sample_step:4,refinements:16,exhaustive:false};
function search(capture,event,reference) {
 const offsets=[-.067,-.05,-.033,-.017,0,.017,.033,.05,.067];
 for(const f of event.frames){const dt=f.time-event.marker;if(dt>=-.134&&dt<=.15&&!offsets.some(t=>Math.abs(t-dt)<.001))offsets.push(dt);}
 const usable=reference.map(p=>p&&!reason(p)),proposals=[];
 for(const offset of offsets) {
  const frames=sequence(capture,event,offset).map(p=>p?.frame);
  for(const dy of [-2,0,2])for(const dx of [-2,0,2]) {
   const errors=[];
   for(let stage=0;stage<7;stage++) {
    const f=frames[stage],r=reference[stage];if(!f||!usable[stage])continue;
    let error=0,count=0,total=0;
    for(let y=1;y<39;y+=4)for(let x=1;x<39;x+=4) {
     total++;const j=y*39+x,i=f.offset*2209+(y+4+dy)*47+x+4+dx;
     if(capture.exclusions[i]||!r.visible[j])continue;
     count++;for(let k=0;k<3;k++)error+=Math.abs(capture.pixels[i*3+k]-r.rgb[j*3+k]);
    }
    if(count>=total*policy.minVisible)errors.push(error/(count*3*255));
   }
   if(errors.length>=policy.minStages)proposals.push({offset,dx,dy,error:errors.reduce((a,b)=>a+b,0)/errors.length});
  }
 }
 proposals.sort((a,b)=>a.error-b.error);
 const selected=[],starts=new Set();
 for(const p of proposals)if(!starts.has(p.offset)&&selected.length<8){selected.push(p);starts.add(p.offset);}
 for(const p of proposals)if(!selected.includes(p)&&selected.length<SEARCH.refinements)selected.push(p);
 const fits=[];
 for(const p of selected) {
  const raw=sequence(capture,event,p.offset,p.dx,p.dy),patches=raw.map((q,i)=>q&&usable[i]&&!reason(q)?regions(q,reference[i]).patch:q);
  const errors=patches.map((q,i)=>compare(q,reference[i])).filter(e=>e!==null),rawErrors=raw.map((q,i)=>compare(q,reference[i])).filter(e=>e!==null);
  if(errors.length<policy.minStages)continue;
  const error=errors.reduce((a,b)=>a+b,0)/errors.length,transition=evolution(patches.map(q=>q&&!reason(q)?q:null),reference.map(q=>q&&!reason(q)?q:null));
  fits.push({...p,error,rawError:rawErrors.reduce((a,b)=>a+b,0)/rawErrors.length,score:error+.3*(transition.error??0),transition,patches});
 }
 fits.sort((a,b)=>a.score-b.score);if(!fits.length)return null;
 const best=fits[0];return {...best,alternatives:fits.filter(f=>f.score<=best.score+policy.ambiguityMargin).map(f=>({error:f.error,offset:f.offset,dx:f.dx,dy:f.dy}))};
}
export function recognizePlay(capture,event,references) {
 const fits=references.map(ref=>({ref,fit:search(capture,event,ref.patches)})).filter(x=>x.fit).sort((a,b)=>a.fit.score-b.fit.score);
 const best=fits.find(x=>accepted(x.fit))??fits[0];
 if(!best)return {status:'insufficient_visible_stages',best:null,order_margin:null,alternatives:[]};
 const reverse=search(capture,event,[...best.ref.patches].reverse()),constant=search(capture,event,best.ref.patches.map(()=>best.ref.patches[0]));
 const margin=reverse&&constant?Math.min(reverse.score,constant.score)-best.fit.score:null;
 const near=fits.filter(x=>accepted(x.fit)&&x.fit.score<=best.fit.score+policy.ambiguityMargin);
 const starts=new Set(near.flatMap(x=>x.fit.alternatives).map(a=>event.frames.reduce((p,q)=>Math.abs(p.time-event.marker-a.offset)<Math.abs(q.time-event.marker-a.offset)?p:q).pts));
 const ordered=accepted(best.fit)&&best.fit.transition.comparisons>=policy.minTransitions&&best.fit.transition.reference_change>=policy.minReferenceChange&&margin!==null&&margin>policy.minOrderMargin&&starts.size===1;
 return {status:!accepted(best.fit)?'large_RGB_alignment_error':ordered?'ordered_image_candidate':'appearance_only_phase_unresolved',
  best:{reference:best.ref.id,fit:best.fit},order_margin:margin,alternatives:near.map(x=>({reference:x.ref.id,error:x.fit.error,offset:x.fit.offset}))};
}
