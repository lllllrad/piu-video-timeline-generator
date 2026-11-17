/** Training-only actual RGB variants; appearance and temporal evidence stay separate. */
import {align,compare,median,policy} from './model.ts';
import type {Capture,Event,Fit,Patch} from './model.ts';
export const accepted=(fit:Fit)=>!!fit&&fit.error<=policy.maxError&&fit.rawError<=policy.maxRawError;
export function variants(items:{id:string;patches:Patch[]}[]) {
 const selected=[];let remaining=items.slice();
 while(remaining.length&&selected.length<3) {
  const scored=remaining.map(item=>{
   const distances=items.filter(x=>x!==item).map(x=>{
    const es=item.patches.map((p,i)=>compare(p,x.patches[i])).filter(e=>e!==null);
    return es.length>=policy.minStages?es.reduce((a,b)=>a+b,0)/es.length:1;
   });
   const separation=selected.length?Math.min(...selected.map(s=>median(item.patches.map((p,i)=>compare(p,s.patches[i])).filter(x=>x!==null))??0)):1;
   return {item,support:1+distances.filter(x=>x<=.1).length,separation};
  }).filter(x=>x.support>=3).sort((a,b)=>b.separation-a.separation);
  if(!scored.length)break;
  const next=scored[0];selected.push({...next.item,support:next.support});remaining=remaining.filter(x=>x!==next.item);
 }
 return selected;
}
export function recognize(capture:Capture,event:Event,references:{id:string;patches:Patch[]}[]) {
 const fits=references.map(ref=>({reference:ref.id,ref,fit:align(capture,event,ref.patches)})).filter(x=>x.fit).sort((a,b)=>a.fit.score-b.fit.score);
 const eligible=fits.filter(x=>accepted(x.fit)),best=eligible[0]??fits[0];
 if(!best)return {status:'insufficient_visible_stages',best:null,alternatives:[]};
 const reverse=align(capture,event,[...best.ref.patches].reverse());
 const constant=align(capture,event,best.ref.patches.map(()=>best.ref.patches[0]));
 const orderMargin=reverse&&constant?Math.min(reverse.score,constant.score)-best.fit.score:null;
 const uniqueOffset=new Set(fits.filter(x=>accepted(x.fit)&&x.fit.score<=best.fit.score+policy.ambiguityMargin).flatMap(x=>x.fit.alternatives).map(a=>event.frames.reduce((p,q)=>Math.abs(p.time-event.marker-a.offset)<Math.abs(q.time-event.marker-a.offset)?p:q).pts)).size===1;
 const ordered=accepted(best.fit)&&best.fit.transition.comparisons>=policy.minTransitions&&best.fit.transition.reference_change>=policy.minReferenceChange&&orderMargin!==null&&orderMargin>policy.minOrderMargin&&uniqueOffset;
 return {status:!accepted(best.fit)?'large_RGB_alignment_error':ordered?'ordered_image_correspondence':'appearance_only_phase_unresolved',
  best:{reference:best.reference,fit:best.fit},order_margin:orderMargin,reverse_score:reverse?.score??null,constant_score:constant?.score??null,
  alternatives:fits.filter(x=>x.fit.score<=best.fit.score+policy.ambiguityMargin).map(x=>({reference:x.reference,error:x.fit.error,score:x.fit.score,offset:x.fit.offset}))};
}
