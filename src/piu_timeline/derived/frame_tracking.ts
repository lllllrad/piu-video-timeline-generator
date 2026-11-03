/** Assign observations only when their coordinate basis and identity are unambiguous. */
import {contracts} from './contracts.ts';
import {sameBasis,type CoordinateBasis} from './coordinates/measurements.ts';

type Position={yPixels:number;uncertaintyPixels:number;basis:CoordinateBasis};
type Observation={time:number;anchor:Position;center:Position|null};
type Track={lane:number;observations:Observation[];maximumGapSeconds:number};
type Detection={lane:number;observation:Observation};
type Edge=[number,number];
type Displacement={fromSeconds:number;pixels:number;uncertaintyPixels:number};
type Displacements=Map<number,Displacement>;

function predict(points:{time:number;position:Position}[],time:number,spacing:number,motion:Displacements):[number,number]|null{
 if(!points.length)return null;
 const last=points.at(-1),dt=time-last.time;
 if(!(dt>0))throw Error('Tracking observations must increase in original recording time');
 const displacement=motion.get(last.time);
 if(displacement){
  if(![displacement.pixels,displacement.uncertaintyPixels].every(Number.isFinite)||displacement.uncertaintyPixels<0)
   throw Error('Invalid measured tracking displacement');
  const y=last.position.yPixels-displacement.pixels,error=last.position.uncertaintyPixels+displacement.uncertaintyPixels;
  return [y-error,y+error];
 }
 let lo=0,hi=contracts.frame_tracking.maximum_speed_spacing_per_second*spacing;
 // Capture can repeat one observed step; this bounds identity prediction only.
 const step=Math.max(0,...points.slice(1).map((p,i)=>Math.abs(p.position.yPixels-points[i].position.yPixels)));
 for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++){
  const a=points[i],b=points[j],elapsed=b.time-a.time;
  if(!(elapsed>0))throw Error('Duplicate or reversed tracking timestamps');
  const delta=a.position.yPixels-b.position.yPixels,error=a.position.uncertaintyPixels+b.position.uncertaintyPixels+step;
  lo=Math.max(lo,(delta-error)/elapsed);hi=Math.min(hi,(delta+error)/elapsed);
 }
 if(lo>hi)return null;
 return [last.position.yPixels-hi*dt-last.position.uncertaintyPixels,last.position.yPixels-lo*dt+last.position.uncertaintyPixels];
}

function compatible(track:Track,detection:Detection,time:number,spacing:number,motion:Displacements):boolean{
 const current=detection.observation;
 if(track.lane!==detection.lane||time-track.observations.at(-1).time>track.maximumGapSeconds+1e-9)return false;
 const centers=current.center?track.observations.filter(o=>o.center&&sameBasis(o.center.basis,current.center.basis)):[];
 const position=centers.length?current.center:current.anchor;
 const history=centers.length?centers.map(o=>({time:o.time,position:o.center})):
  track.observations.filter(o=>sameBasis(o.anchor.basis,current.anchor.basis)).map(o=>({time:o.time,position:o.anchor}));
 const range=predict(history,time,spacing,motion);
 return !!range&&range[0]<=position.yPixels+position.uncertaintyPixels+1e-9&&position.yPixels-position.uncertaintyPixels<=range[1]+1e-9;
}

function matching(edges:boolean[][],ordered:boolean,except?:Edge):Edge[]{
 const n=edges.length,m=edges[0]?.length??0,allowed=(i,j)=>edges[i][j]&&!(except&&except[0]===i&&except[1]===j);
 if(ordered){
  const score=Array.from({length:n+1},()=>Array(m+1).fill(0));
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)
   score[i][j]=Math.max(score[i+1][j],score[i][j+1],allowed(i,j)?1+score[i+1][j+1]:0);
  const result:Edge[]=[];let i=0,j=0;
  while(i<n&&j<m){
   if(allowed(i,j)&&score[i][j]===1+score[i+1][j+1]){result.push([i++,j++]);}
   else if(score[i+1][j]>=score[i][j+1])i++;else j++;
  }
  return result;
 }
 const owners=Array(m).fill(-1);
 const augment=(i:number,seen:Set<number>):boolean=>{
  for(let j=0;j<m;j++)if(allowed(i,j)&&!seen.has(j)){
   seen.add(j);if(owners[j]<0||augment(owners[j],seen)){owners[j]=i;return true;}
  }
  return false;
 };
 for(let i=0;i<n;i++)augment(i,new Set());
 return owners.flatMap((i,j)=>i>=0?[[i,j] as Edge]:[]);
}

function orderedView(tracks:Track[],detections:Detection[]):'center'|'anchor'|null{
 const previous=tracks.map(t=>t.observations.at(-1));
 if(new Set(previous.map(o=>o.time)).size!==1)return null;
 for(const view of ['center','anchor']as const){
  const before=previous.map(o=>o[view]),after=detections.map(d=>d.observation[view]);
  if([...before,...after].some(p=>!p)||![...before,...after].every(p=>sameBasis(p.basis,before[0].basis)))continue;
  const separated=(positions:Position[])=>positions.sort((a,b)=>a.yPixels-b.yPixels).slice(1).every((p,i)=>positions[i].yPixels+positions[i].uncertaintyPixels<p.yPixels-p.uncertaintyPixels);
  if(separated([...before])&&separated([...after]))return view;
 }
 return null;
}

export function assign(tracks:Track[],detections:Detection[],time:number,spacing:number,motion:Displacement[]=[]){
 if(!Number.isFinite(time)||!Number.isFinite(spacing)||spacing<=0)throw Error('Tracking requires finite time and positive lane spacing');
 for(const o of [...tracks.flatMap(t=>t.observations),...detections.map(d=>d.observation)]){
  if(!Number.isFinite(o.time))throw Error('Tracking requires original observation times');
  if(o.center&&o.center.basis.kind!=='native_cap_center')throw Error('Unqualified cap center basis');
  for(const p of [o.anchor,o.center].filter(Boolean))if(![p.yPixels,p.uncertaintyPixels].every(Number.isFinite)||p.uncertaintyPixels<0||p.basis.kind==='unavailable')throw Error('Unqualified tracking coordinates');
 }
 if(tracks.some(t=>!t.observations.length)||detections.some(d=>d.observation.time!==time))throw Error('Missing or mismatched tracking observation');
 if(tracks.some(t=>!Number.isFinite(t.maximumGapSeconds)||t.maximumGapSeconds<0||t.observations.slice(1).some((o,i)=>o.time<=t.observations[i].time)))throw Error('Invalid tracking history or expiry');
 const displacements=new Map(motion.map(s=>[s.fromSeconds,s]));
 if(displacements.size!==motion.length)throw Error('Duplicate tracking displacement origin');
 const matches:Edge[]=[],uncertainTracks=new Set<number>(),uncertainDetections=new Set<number>(),ambiguities:Edge[]=[];
 for(const lane of new Set([...tracks,...detections].map(x=>x.lane))){
  const a=tracks.flatMap((t,i)=>t.lane===lane?[i]:[]),b=detections.flatMap((d,i)=>d.lane===lane?[i]:[]);
  if(!a.length||!b.length)continue;
  const view=orderedView(a.map(i=>tracks[i]),b.map(j=>detections[j]));
  if(view){a.sort((i,j)=>tracks[i].observations.at(-1)[view].yPixels-tracks[j].observations.at(-1)[view].yPixels);b.sort((i,j)=>detections[i].observation[view].yPixels-detections[j].observation[view].yPixels);}
  const edges=a.map(i=>b.map(j=>compatible(tracks[i],detections[j],time,spacing,displacements)));
  const chosen=matching(edges,!!view),forced=chosen.filter(edge=>matching(edges,!!view,edge).length<chosen.length);
  for(const [i,j]of forced)matches.push([a[i],b[j]]);
  const fixedA=new Set(forced.map(([i])=>i)),fixedB=new Set(forced.map(([,j])=>j));
  if(forced.length===chosen.length)continue;
  // Retire the uncertain fragments before beginning the newly observed ones.
  // They remain separate evidence, rather than contaminating a later identity.
  for(let i=0;i<a.length;i++)for(let j=0;j<b.length;j++)if(edges[i][j]&&!fixedA.has(i)&&!fixedB.has(j)){
   uncertainTracks.add(a[i]);uncertainDetections.add(b[j]);ambiguities.push([a[i],b[j]]);
  }
 }
 return {matches,ambiguousTracks:[...uncertainTracks],ambiguousDetections:[...uncertainDetections],ambiguities};
}
