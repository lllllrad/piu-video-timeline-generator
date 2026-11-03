/** Assign observations only when their coordinate basis and identity are unambiguous. */
import {contracts} from './contracts.ts';
import {sameBasis,type CoordinateBasis} from './coordinates/measurements.ts';

type Position={yPixels:number;uncertaintyPixels:number;basis:CoordinateBasis};
type Observation={time:number;anchor:Position;anchors?:Position[];center:Position|null};
type Track={lane:number;observations:Observation[];maximumGapSeconds:number};
type Detection={lane:number;observation:Observation};
type Edge=[number,number];
type Displacement={fromSeconds:number;pixels:number;uncertaintyPixels:number;unobservedTerminalStep?:boolean};
type Step=Displacement&{toSeconds:number;basis:'coobserved_images'|'forced_identity_images'};
type Displacements=Map<number,Displacement>;

function displacement(a:Observation,b:Observation):[number,number]|null{
 const views=a.center&&b.center?[[a.center,b.center]]:
  (a.anchors??[a.anchor]).flatMap(p=>{
   const q=(b.anchors??[b.anchor]).find(q=>sameBasis(p.basis,q.basis));return q?[[p,q]]:[];
  });
 if(!views.length)return null;
 const ranges=views.map(([p,q])=>{const delta=p.yPixels-q.yPixels,error=p.uncertaintyPixels+q.uncertaintyPixels;return [delta-error,delta+error];}),
  lo=Math.max(...ranges.map(r=>r[0])),hi=Math.min(...ranges.map(r=>r[1]));
 return lo<=hi?[lo,hi]:null;
}

function predict(points:{time:number;position:Position}[],time:number,spacing:number,motion:Displacements):[number,number]|null{
 if(!points.length)return null;
 const last=points.at(-1),dt=time-last.time;
 if(!(dt>0))throw Error('Tracking observations must increase in original recording time');
 const displacement=motion.get(last.time);
 // An inferred final step is a search envelope. Repeated native positions
 // constrain a long visibility gap independently of that unobserved step.
 if(displacement&&!(dt>.05+1e-6&&points.length>=4&&displacement.unobservedTerminalStep)){
  if(![displacement.pixels,displacement.uncertaintyPixels].every(Number.isFinite)||displacement.uncertaintyPixels<0)
   throw Error('Invalid measured tracking displacement');
  const y=last.position.yPixels-displacement.pixels,error=last.position.uncertaintyPixels+displacement.uncertaintyPixels;
  return [y-error,y+error];
 }
 // A visibility gap needs observed displacement or a repeated compatible
 // trajectory. A lone cap cannot establish a reversal and return to the field.
 if(dt>.05+1e-6){
  if(points.length<4)return null;
  const speed=contracts.frame_tracking.maximum_speed_spacing_per_second*spacing;
  let lo=-speed,hi=speed;
  const step=Math.max(...points.slice(1).map((p,i)=>Math.abs(p.position.yPixels-points[i].position.yPixels)));
  for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++){
   const a=points[i],b=points[j],elapsed=b.time-a.time,
    delta=a.position.yPixels-b.position.yPixels,error=a.position.uncertaintyPixels+b.position.uncertaintyPixels+step;
   lo=Math.max(lo,(delta-error)/elapsed);hi=Math.min(hi,(delta+error)/elapsed);
  }
  return lo<=hi?[last.position.yPixels-hi*dt-last.position.uncertaintyPixels,last.position.yPixels-lo*dt+last.position.uncertaintyPixels]:null;
 }
 // A trajectory may stop, accelerate or reverse. Past velocity is not a bound
 // on its next step; the physical gate cannot certify a musical clock.
 const radius=contracts.frame_tracking.maximum_speed_spacing_per_second*spacing*dt+last.position.uncertaintyPixels;
 return [last.position.yPixels-radius,last.position.yPixels+radius];
}

function compatible(track:Track,detection:Detection,time:number,spacing:number,motion:Displacements):boolean{
 const current=detection.observation;
 if(track.lane!==detection.lane||time-track.observations.at(-1).time>track.maximumGapSeconds+1e-9)return false;
 const centers=current.center?track.observations.filter(o=>o.center&&sameBasis(o.center.basis,current.center.basis)):[];
 const views=centers.length?[{position:current.center,history:centers.map(o=>({time:o.time,position:o.center}))}]:
  (current.anchors??[current.anchor]).map(position=>({position,history:track.observations.flatMap(o=>{
   const p=(o.anchors??[o.anchor]).find(p=>sameBasis(p.basis,position.basis));return p?[{time:o.time,position:p}]:[];
  })})).filter(v=>v.history.length);
 return !!views.length&&views.every(({position,history})=>{
  const range=predict(history,time,spacing,motion);
  return !!range&&range[0]<=position.yPixels+position.uncertaintyPixels+1e-9&&position.yPixels-position.uncertaintyPixels<=range[1]+1e-9;
 });
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

/** Common signed translation in compatible views, before choosing identities. */
function translationsAtLimit(tracks:Track[],detections:Detection[],time:number,spacing:number,intervalSeconds:number):Displacement[]{
 const fromSeconds=Math.max(...tracks.map(t=>t.observations.at(-1).time)),dt=time-fromSeconds;
 if(!(0<dt&&dt<=.05+1e-6))return [];
 const before=tracks.filter(t=>t.observations.at(-1).time===fromSeconds),
  after=detections,limit=contracts.frame_tracking.maximum_speed_spacing_per_second*spacing*intervalSeconds;
 const intervals=before.map(t=>after.map(d=>{
  if(t.lane!==d.lane)return null;
  const range=displacement(t.observations.at(-1),d.observation);if(!range)return null;
  const lo=Math.max(-limit,range[0]),hi=Math.min(limit,range[1]);
  return lo<=hi?[lo,hi]:null;
 }));
 const boundaries=[...new Set(intervals.flat().filter(Boolean).flat())].sort((a,b)=>a-b);
 let score=[0,0],ranges:number[][]=[];
 const inspect=(lo:number,hi:number)=>{
  const value=(lo+hi)/2,edges=intervals.map(row=>row.map(r=>!!r&&r[0]-1e-9<=value&&value<=r[1]+1e-9));
  const pairs=matching(edges,false),lanes=new Set(pairs.map(([i])=>before[i].lane)).size;
  if(pairs.length<2||lanes<2)return;
  if(pairs.length>score[0]||pairs.length===score[0]&&lanes>score[1]){score=[pairs.length,lanes];ranges=[];}
  if(pairs.length===score[0]&&lanes===score[1])ranges.push([lo,hi]);
 };
 boundaries.forEach((p,i)=>{inspect(p,p);if(i)inspect(boundaries[i-1],p);});
 if(!ranges.length)return [];
 ranges.sort((a,b)=>a[0]-b[0]);const merged:number[][]=[];
 for(const r of ranges){const last=merged.at(-1);if(!last||r[0]>last[1]+1e-9)merged.push([...r]);else last[1]=Math.max(last[1],r[1]);}
 return merged.map(([lo,hi])=>({fromSeconds,pixels:(lo+hi)/2,uncertaintyPixels:(hi-lo)/2}));
}


function ordinaryHistory(tracks:Track[],step:Displacement,time:number):boolean{
 let lo=-Infinity,hi=Infinity,captureBound=0;const lanes=new Set<number>();
 for(const track of tracks){
  const history=track.observations;
  if(history.length<3||history.at(-1).time!==step.fromSeconds)continue;
  const net=displacement(history[0],history.at(-1));
  if(!net||net[0]>0&&step.pixels+step.uncertaintyPixels<0||net[1]<0&&step.pixels-step.uncertaintyPixels>0)continue;
  let a=-Infinity,b=Infinity;
  const adjacent=history.slice(1).map((o,i)=>displacement(history[i],o));
  if(adjacent.some((r,i)=>!r||history[i+1].time-history[i].time>.05+1e-6))continue;
  // A repeated game render is not zero engine velocity. Retain one actually
  // observed render step as capture-phase uncertainty over the full history.
  const capture=Math.max(...adjacent.map(r=>Math.abs((r[0]+r[1])/2)));
  for(let i=0;i<history.length;i++)for(let j=i+1;j<history.length;j++){
   const range=displacement(history[i],history[j]),dt=history[j].time-history[i].time;
   if(!range){a=Infinity;continue;}
   a=Math.max(a,(range[0]-capture)/dt);b=Math.min(b,(range[1]+capture)/dt);
  }
  if(a>b)continue;
  lo=Math.max(lo,a);hi=Math.min(hi,b);captureBound=Math.max(captureBound,capture);lanes.add(track.lane);
 }
 const dt=time-step.fromSeconds;
 return lanes.size>=2&&lo<=hi&&lo*dt-captureBound<=step.pixels+step.uncertaintyPixels&&step.pixels-step.uncertaintyPixels<=hi*dt+captureBound;
}
function translations(tracks:Track[],detections:Detection[],time:number,spacing:number):Displacement[]{
 const dt=time-Math.max(...tracks.map(t=>t.observations.at(-1).time)),ordinary=translationsAtLimit(tracks,detections,time,spacing,dt);
 if(ordinary.length===1&&ordinaryHistory(tracks,ordinary[0],time))return ordinary;
 return translationsAtLimit(tracks,detections,time,spacing,contracts.frame_tracking.maximum_capture_interval_seconds);
}

function orderedView(tracks:Track[],detections:Detection[]):{before:Position[];after:Position[]}|null{
 const previous=tracks.map(t=>t.observations.at(-1));
 if(new Set(previous.map(o=>o.time)).size!==1)return null;
 const views=(o:Observation)=>[o.center,...o.anchors??[o.anchor]].filter(Boolean);
 for(const reference of views(previous[0])){
  const before=previous.map(o=>views(o).find(p=>sameBasis(p.basis,reference.basis))),
   after=detections.map(d=>views(d.observation).find(p=>sameBasis(p.basis,reference.basis)));
  if([...before,...after].some(p=>!p))continue;
  const separated=(positions:Position[])=>positions.sort((a,b)=>a.yPixels-b.yPixels).slice(1).every((p,i)=>positions[i].yPixels+positions[i].uncertaintyPixels<p.yPixels-p.uncertaintyPixels);
  if(separated([...before])&&separated([...after]))return {before,after};
 }
 return null;
}

export function assign(tracks:Track[],detections:Detection[],time:number,spacing:number,motion:Displacement[]=[],pastSteps:Step[]=[]){
 if(!Number.isFinite(time)||!Number.isFinite(spacing)||spacing<=0)throw Error('Tracking requires finite time and positive lane spacing');
 for(const o of [...tracks.flatMap(t=>t.observations),...detections.map(d=>d.observation)]){
  if(!Number.isFinite(o.time))throw Error('Tracking requires original observation times');
  if(o.center&&o.center.basis.kind!=='native_cap_center')throw Error('Unqualified cap center basis');
  for(const p of [o.anchor,o.center,...o.anchors??[]].filter(Boolean))if(![p.yPixels,p.uncertaintyPixels].every(Number.isFinite)||p.uncertaintyPixels<0||p.basis.kind==='unavailable')throw Error('Unqualified tracking coordinates');
 }
 if(tracks.some(t=>!t.observations.length)||detections.some(d=>d.observation.time!==time))throw Error('Missing or mismatched tracking observation');
 if(tracks.some(t=>!Number.isFinite(t.maximumGapSeconds)||t.maximumGapSeconds<0||t.observations.slice(1).some((o,i)=>o.time<=t.observations[i].time)))throw Error('Invalid tracking history or expiry');
 const displacements=new Map(motion.map(s=>[s.fromSeconds,s]));
 if(displacements.size!==motion.length)throw Error('Duplicate tracking displacement origin');
 const alternatives=translations(tracks,detections,time,spacing),measured=alternatives.length===1?alternatives[0]:null;
 let step:Step|null=measured?{...measured,toSeconds:time,basis:'coobserved_images'}:null;
 const steps=new Map(pastSteps.map(s=>[s.toSeconds,s]));
 if(steps.size!==pastSteps.length)throw Error('Duplicate frame displacement time');
 for(const s of pastSteps)if(![s.fromSeconds,s.toSeconds,s.pixels,s.uncertaintyPixels].every(Number.isFinite)||
  s.fromSeconds>=s.toSeconds||s.toSeconds>=time||s.uncertaintyPixels<0)throw Error('Invalid retained frame displacement');
 if(step)steps.set(time,step);
 let origin=time,pixels=0,uncertaintyPixels=0;
 if(!step&&pastSteps.length){
  const latest=Math.max(...pastSteps.map(s=>s.toSeconds)),gap=time-latest;
  if(0<gap&&gap<=.05+1e-6){
   origin=latest;uncertaintyPixels=contracts.frame_tracking.maximum_speed_spacing_per_second*spacing*gap;
   displacements.set(origin,{fromSeconds:origin,pixels,uncertaintyPixels,unobservedTerminalStep:true});
  }
 }
 while(steps.has(origin)){
  const previous=steps.get(origin);pixels+=previous.pixels;uncertaintyPixels+=previous.uncertaintyPixels;origin=previous.fromSeconds;
  displacements.set(origin,{fromSeconds:origin,pixels,uncertaintyPixels,...(!step?{unobservedTerminalStep:true}:{})});
 }
 const matches:Edge[]=[],uncertainTracks=new Set<number>(),uncertainDetections=new Set<number>(),ambiguities:Edge[]=[];
 for(const lane of new Set([...tracks,...detections].map(x=>x.lane))){
  const a=tracks.flatMap((t,i)=>t.lane===lane?[i]:[]),b=detections.flatMap((d,i)=>d.lane===lane?[i]:[]);
  if(!a.length||!b.length)continue;
  const view=orderedView(a.map(i=>tracks[i]),b.map(j=>detections[j]));
  if(view){
   const before=new Map(a.map((id,i)=>[id,view.before[i]])),after=new Map(b.map((id,i)=>[id,view.after[i]]));
   a.sort((i,j)=>before.get(i).yPixels-before.get(j).yPixels);b.sort((i,j)=>after.get(i).yPixels-after.get(j).yPixels);
  }
  const hypotheses=alternatives.length>1?alternatives.map(d=>new Map(displacements).set(d.fromSeconds,d)):[displacements];
  const tables=hypotheses.map(m=>a.map(i=>b.map(j=>compatible(tracks[i],detections[j],time,spacing,m))));
  const forcedByModel=tables.map(edges=>{
   const chosen=matching(edges,!!view);
   return chosen.filter(edge=>matching(edges,!!view,edge).length<chosen.length);
  });
  // Each assignment must use one coherent image translation. Combining edges
  // from different translations could fabricate a larger matching and force
  // a false identity when one actual cap is missing.
  const forced=forcedByModel[0].filter(([i,j])=>forcedByModel.every(edges=>edges.some(([a,b])=>a===i&&b===j)));
  const edges=a.map((_,i)=>b.map((_,j)=>tables.some(edges=>edges[i][j])));
  for(const [i,j]of forced)matches.push([a[i],b[j]]);
  const fixedA=new Set(forced.map(([i])=>i)),fixedB=new Set(forced.map(([,j])=>j));
  // Retire the uncertain fragments before beginning the newly observed ones.
  // They remain separate evidence, rather than contaminating a later identity.
  for(let i=0;i<a.length;i++)for(let j=0;j<b.length;j++)if(edges[i][j]&&!fixedA.has(i)&&!fixedB.has(j)){
   uncertainTracks.add(a[i]);uncertainDetections.add(b[j]);ambiguities.push([a[i],b[j]]);
  }
 }
 if(!step){
  const fromSeconds=Math.max(...tracks.map(t=>t.observations.at(-1).time)),dt=time-fromSeconds;
  const pairs=matches.filter(([i])=>tracks[i].observations.at(-1).time===fromSeconds);
  if(pairs.length&&0<dt&&dt<=.05+1e-6){
   const intervals=pairs.map(([i,j])=>displacement(tracks[i].observations.at(-1),detections[j].observation)).filter(Boolean);
   const lo=Math.max(...intervals.map(r=>r[0])),hi=Math.min(...intervals.map(r=>r[1]));
   if(intervals.length&&lo<=hi)step={fromSeconds,toSeconds:time,pixels:(lo+hi)/2,uncertaintyPixels:(hi-lo)/2,basis:'forced_identity_images'};
  }
 }
 const limit=measured?contracts.frame_tracking.maximum_speed_spacing_per_second*spacing*(time-measured.fromSeconds):Infinity;
 const cadenceWarnings=measured&&Math.abs(measured.pixels)-measured.uncertaintyPixels>limit+1e-8?[{
  reason:'observed_frame_step_exceeds_source_cadence',check:'note_visibility',
  visible_start_seconds:measured.fromSeconds,visible_end_seconds:time,
  displacement_range_pixels:[measured.pixels-measured.uncertaintyPixels,measured.pixels+measured.uncertaintyPixels],
  source_cadence_limit_pixels:limit,interpretation:'measured_image_translation_without_engine_time_assumption'}]:[];
 return {translationAlternatives:alternatives,cadenceWarnings,matches,ambiguousTracks:[...uncertainTracks],ambiguousDetections:[...uncertainDetections],ambiguities,measuredDisplacement:measured,step};
}
