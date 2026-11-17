/** RGB-only reference modeling. Source observation clocks never become input clocks. */
export const stages = [0, .033, .067, .100, .150, .200, .250];
export const policy = {maxError: .10, minVisible: .65, minStages: 5, minContributors: 3,
  ambiguityMargin: .005, maxSaturatedFraction: .85};
export type Frame = {offset:number; pts:number; time:number; crop:number[]; envelopes:number[][]};
export type Event = {id:string; kind:number; lane:number; marker:number; frames:Frame[]};
export type Patch = {rgb:Uint8Array; visible:Uint8Array; frame?:Frame};
export type Capture = {events:Event[]; pixels:Uint8Array; exclusions:Uint8Array};
export type Fit = {error:number; offset:number; dx:number; dy:number; patches:Patch[];
  alternatives:{error:number; offset:number; dx:number; dy:number}[]};
export function median(values:number[]) {
  if(!values.length)return null;
  const v=values.slice().sort((a,b)=>a-b), i=Math.floor(v.length/2);
  return v.length%2?v[i]:(v[i-1]+v[i])/2;
}
export function patch(capture:Capture, frame:Frame, dx=0, dy=0):Patch {
  const rgb=new Uint8Array(39*39*3), visible=new Uint8Array(39*39);
  for(let y=0;y<39;y++)for(let x=0;x<39;x++) {
    const from=frame.offset*47*47+(y+4+dy)*47+x+4+dx, to=y*39+x;
    visible[to]=capture.exclusions[from]?0:1;
    for(let c=0;c<3;c++)rgb[to*3+c]=capture.pixels[from*3+c];
  }
  return {rgb,visible,frame};
}
export function reason(p:Patch) {
  let count=0, saturated=0;
  for(let i=0;i<p.visible.length;i++)if(p.visible[i]) {
    count++;if([0,1,2].every(c=>p.rgb[i*3+c]>235))saturated++;
  }
  if(count<39*39*policy.minVisible)return 'insufficient_visible_support';
  if(saturated/count>policy.maxSaturatedFraction)return 'saturated_shared_flash_candidate';
  return null;
}
export function sequence(capture:Capture, event:Event, offset=0, dx=0, dy=0) {
  return stages.map(dt=>{
    const target=event.marker+offset+dt;
    const f=event.frames.reduce((a,b)=>Math.abs(a.time-target)<Math.abs(b.time-target)?a:b);
    if(Math.abs(f.time-target)>.012)return null;
    return patch(capture,f,dx,dy);
  });
}
export function compare(a:Patch,b:Patch) {
  if(!a||!b||reason(a)||reason(b))return null;
  let count=0,total=0;
  for(let i=0;i<a.visible.length;i++)if(a.visible[i]&&b.visible[i]) {
    count++;for(let c=0;c<3;c++)total+=Math.abs(a.rgb[i*3+c]-b.rgb[i*3+c]);
  }
  return count>=39*39*policy.minVisible?total/(count*3*255):null;
}
export function align(capture:Capture,event:Event,reference:Patch[]):Fit|null {
  const options:Omit<Fit,'alternatives'>[]=[];
  for(const offset of [-.067,-.050,-.033,-.017,0,.017,.033,.050,.067])
    for(const dy of [-2,0,2])for(const dx of [-2,0,2]) {
      const patches=sequence(capture,event,offset,dx,dy);
      const errors=patches.map((p,i)=>compare(p,reference[i])).filter(e=>e!==null);
      if(errors.length<policy.minStages)continue;
      options.push({error:errors.reduce((a,b)=>a+b,0)/errors.length,offset,dx,dy,patches});
    }
  options.sort((a,b)=>a.error-b.error);
  if(!options.length)return null;
  const best=options[0];
  return {...best,alternatives:options.filter(o=>o.error<=best.error+policy.ambiguityMargin)
    .map(({error,offset,dx,dy})=>({error,offset,dx,dy}))};
}
export function aggregate(patches:Patch[]) {
  const rgb=new Uint8Array(39*39*3), visible=new Uint8Array(39*39), contributors=new Uint16Array(39*39);
  const usable=patches.filter(p=>p&&!reason(p));
  for(let i=0;i<visible.length;i++) {
    const samples=usable.filter(p=>p.visible[i]);contributors[i]=samples.length;
    if(samples.length<policy.minContributors)continue;
    visible[i]=1;for(let c=0;c<3;c++)rgb[i*3+c]=Math.round(median(samples.map(p=>p.rgb[i*3+c])));
  }
  return {rgb,visible,contributors};
}
export function disjoint(a:Event,b:Event) {
  const pts=new Set(a.frames.map(f=>f.pts));return !b.frames.some(f=>pts.has(f.pts));
}
