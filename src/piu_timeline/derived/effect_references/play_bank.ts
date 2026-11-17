/** Load exact source-bound RGB models, not timing-calibrated or named-skin assets. */
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {parseData} from '../json.ts';
import {aggregate,patch,stages} from './model.ts';
import {load,hash} from './io.ts';
export function referenceBank(path:string) {
 const result=parseData(readFileSync(path,'utf8'));
 if(result.schema!==2)throw new Error('Effect reference requires sequence bank schema 2; regenerate references');
 if(hash(result.input)!==result.capture_sha256)throw new Error('Effect reference capture changed');
 const source=load(result.input);
 for(const [file,digest] of Object.entries(result.implementation_sha256??{})) {
  if(!['cli.ts','model.ts','io.ts','bank.ts','regions.ts','temporal.ts'].includes(file))throw new Error('Unknown effect reference producer');
  if(hash(new URL(file,import.meta.url).pathname)!==digest)throw new Error('Effect reference model changed; regenerate references');
 }
 const witness=(id,frame)=>{
  const event=source.capture.events.find(e=>e.id===id);
  if(!event||!event.frames.some(f=>f.offset===frame.offset&&f.pts===frame.pts&&f.time===frame.time&&JSON.stringify(f.crop)===JSON.stringify(frame.crop)))throw new Error('Foreign effect reference frame');
 };
 const byKind=new Map(),trainingFrames=new Map();
 for(const g of result.groups) {
  const observations=g.accepted??[];trainingFrames.set(g.kind,new Set(observations.flatMap(a=>a.frames.filter(f=>f.frame).map(f=>f.frame.pts))));
  for(const a of observations)if(!Array.isArray(a.translation)||a.translation.length!==2||a.translation.some(x=>![-2,0,2].includes(x))||source.capture.events.find(e=>e.id===a.id)?.kind!==g.kind)throw new Error('Invalid effect reference registration');
  const series=observations.map(a=>a.frames.map(f=>{
   if(!f.frame)return null;witness(a.id,f.frame);
   const p=patch(source.capture,f.frame,...a.translation as [number,number]),visible=p.visible.slice();
   for(const outlier of f.image_outlier_regions??[]) {
    const [l,t,r,b]=outlier.box;if(![l,t,r,b].every(Number.isInteger)||l<0||t<0||r>39||b>39||l>=r||t>=b)throw new Error('Invalid image-outlier region');for(let y=t;y<b;y++)for(let x=l;x<r;x++)visible[y*39+x]=0;
   }
   return {...p,visible};
  }));
  const refs=[];
  if(series.length)refs.push({id:'consensus',patches:stages.map((_,i)=>aggregate(series.map(s=>s[i])))});
  for(const v of g.variants??[]) {
   if(v.training_support<3||!observations.some(a=>a.id===v.id))throw new Error('Unsupported effect variant');
   const a=observations.find(a=>a.id===v.id);
   refs.push({id:v.id,patches:v.files.map(f=>{
    if(!f)return null;witness(a.id,f.frame);
    const p=patch(source.capture,f.frame,...a.translation as [number,number]);
    if(f.visible_mask?.length!==1521||f.visible_mask.some((value,i)=>![0,1].includes(value)||value>p.visible[i]))throw new Error('Invalid effect reference visibility');
    return {...p,visible:Uint8Array.from(f.visible_mask)};
   })});
  }
  if(refs.length)byKind.set(g.kind,refs);
 }
 if(!byKind.size)throw new Error('Effect reference has no usable image models');
 return {byKind,trainingFrames,manifest:source.manifest,source:result.source,identity:result.source_identity,reference:resolve(path)};
}
