/** Assign observations only when their coordinate basis and identity are unambiguous. */
import {contracts} from './contracts.ts';
import {roundoff} from './math.ts';
import {sameBasis,type CoordinateBasis} from './coordinates/measurements.ts';

type Position={yPixels:number;uncertaintyPixels:number;basis:CoordinateBasis};
type Observation={time:number;anchor:Position;anchors?:Position[];center:Position|null;sourcePtsSeconds?:number};
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
 return lo<=hi?[lo,hi]:lo-hi<=roundoff(...views.flatMap(([p,q])=>[p.yPixels,q.yPixels]))?[(lo+hi)/2,(lo+hi)/2]:null;
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
 // Past velocity only bounds a candidate search. Gap identity is certified
 // separately by directly observed independent endpoint travel.
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
  return lo<=hi?[last.position.yPixels-hi*dt-last.position.uncertaintyPixels-step,last.position.yPixels-lo*dt+last.position.uncertaintyPixels+step]:null;
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

/** Test whether a rigid image constellation exists; never certify identity here. */
function matching(edges:boolean[][]):Edge[]{
 const n=edges.length,m=edges[0]?.length??0,allowed=(i,j)=>edges[i][j];
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
 const epsilon=roundoff(...tracks.flatMap(t=>t.observations.map(o=>o.center?.yPixels??o.anchor.yPixels)),
  ...detections.map(d=>d.observation.center?.yPixels??d.observation.anchor.yPixels));
 const boundaries=[...new Set(intervals.flat().filter(Boolean).flat())].sort((a,b)=>a-b)
  .filter((p,i,sorted)=>!i||p-sorted[i-1]>epsilon);
 const ranges:number[][]=[],completePatterns:number[][]=[];
 const inspect=(lo:number,hi:number)=>{
  const value=(lo+hi)/2,edges=intervals.map(row=>row.map(r=>!!r&&r[0]-epsilon<=value&&value<=r[1]+epsilon));
  const pairs=matching(edges);
  const independent=pairs.some(([i],k)=>pairs.slice(k+1).some(([j])=>{
   if(before[i].lane!==before[j].lane)return true;
   const a=before[i].observations.at(-1),b=before[j].observations.at(-1),range=displacement(a,b);
   return !!range&&(range[0]>0||range[1]<0);
  }));
  if(!independent)return;
  ranges.push([lo,hi]);
  // A rigid, complete observed constellation is an image reference, unlike
  // the largest partial matching. Keep every such translation, without ranking
  // candidates by how many unrelated objects they happen to connect.
  const completeLanes=new Set([...new Set(before.map(t=>t.lane))].filter(lane=>{
   const n=before.filter(t=>t.lane===lane).length,m=after.filter(d=>d.lane===lane).length;
   return n===m&&pairs.filter(([i])=>before[i].lane===lane).length===n;
  }));
  const complete=pairs.filter(([i])=>completeLanes.has(before[i].lane));
  if(complete.length>=2&&(completeLanes.size>=2||independent))completePatterns.push([lo,hi]);
 };
 boundaries.forEach((p,i)=>{inspect(p,p);if(i)inspect(boundaries[i-1],p);});
 const supported=completePatterns.length?completePatterns:ranges;
 if(!supported.length)return [];
 supported.sort((a,b)=>a[0]-b[0]);const merged:number[][]=[];
 for(const r of supported){const last=merged.at(-1);if(!last||r[0]>last[1]+1e-9)merged.push([...r]);else last[1]=Math.max(last[1],r[1]);}
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

/** Endpoint measurements of independently continuous peers, never a sum of step errors. */
function gapDisplacement(trackIndex:number,tracks:Track[],detections:Detection[],pairs:Edge[],time:number){
 const fromSeconds=tracks[trackIndex].observations.at(-1).time;
 const references=pairs.flatMap(([i,j])=>{
  if(i===trackIndex)return [];
  const history=tracks[i].observations,at=history.findIndex(o=>Math.abs(o.time-fromSeconds)<1e-9);
  if(at<0)return [];
  const span=[...history.slice(at),detections[j].observation];
  if(history.length<4||span.length<2||span.slice(1).some((o,k)=>o.time-span[k].time>.05+1e-6))return [];
  if(span.some(o=>o.sourcePtsSeconds!==undefined)&&span.some((o,k)=>
   !Number.isFinite(o.sourcePtsSeconds)||k>0&&(o.sourcePtsSeconds<=span[k-1].sourcePtsSeconds||
    Math.abs((o.sourcePtsSeconds-span[k-1].sourcePtsSeconds)-(o.time-span[k-1].time))>1e-6)))return [];
  const range=displacement(span[0],span.at(-1));
  return range?[{track:i,detection:j,lane:tracks[i].lane,from:span[0],to:span.at(-1),range}]:[];
 });
 if(new Set(references.map(r=>r.lane)).size<2)return null;
 const lo=Math.max(...references.map(r=>r.range[0])),hi=Math.min(...references.map(r=>r.range[1]));
 const epsilon=roundoff(...references.flatMap(r=>[r.from.center?.yPixels??r.from.anchor.yPixels,r.to.center?.yPixels??r.to.anchor.yPixels]));
 if(lo>hi+epsilon)return null;
 const range=lo>hi?[(lo+hi)/2,(lo+hi)/2]:[lo,hi];
 return {fromSeconds,pixels:(lo+hi)/2,uncertaintyPixels:(range[1]-range[0])/2,
  proof:{fromSeconds,toSeconds:time,displacementRangePixels:range,references}};
}

// Maximum matching answers how many edges can be selected, not whether an
// identity exists. Missing old caps and newly visible caps are always possible.
function uniqueEdges(edges:boolean[][]):Edge[]{
 return edges.flatMap((row,i)=>row.flatMap((allowed,j)=>allowed&&
  row.filter(Boolean).length===1&&edges.filter(r=>r[j]).length===1?[[i,j] as Edge]:[]));
}

export function assign(tracks:Track[],detections:Detection[],time:number,spacing:number,motion:Displacement[]=[],pastSteps:Step[]=[]){
 if(!Number.isFinite(time)||!Number.isFinite(spacing)||spacing<=0)throw Error('Tracking requires finite time and positive lane spacing');
 for(const o of [...tracks.flatMap(t=>t.observations),...detections.map(d=>d.observation)]){
  if(o.sourcePtsSeconds!==undefined&&!Number.isFinite(o.sourcePtsSeconds))throw Error('Tracking requires finite source PTS');
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
 const latestObservation=Math.max(...tracks.map(t=>t.observations.at(-1).time));
 const isGap=(t:Track)=>time-t.observations.at(-1).time>.05+1e-6||t.observations.at(-1).time<latestObservation-1e-9;
 const adjacentPairs:Edge[]=[],gapConnections:(NonNullable<ReturnType<typeof gapDisplacement>>['proof']&{track:number;detection:number})[]=[];
 // Only independently unique adjacent identities can certify a gap. Gap edges
 // never bootstrap other gap edges, and ordering/cardinality supplies no proof.
 const adjacentTables=(alternatives.length>1?alternatives.map(d=>new Map(displacements).set(d.fromSeconds,d)):[displacements])
  .map(m=>tracks.map(t=>detections.map(d=>!isGap(t)&&compatible(t,d,time,spacing,m))));
 for(const edge of uniqueEdges(adjacentTables[0]))if(adjacentTables.every(table=>uniqueEdges(table).some(([i,j])=>i===edge[0]&&j===edge[1])))adjacentPairs.push(edge);
 const gapMotion=new Map(tracks.flatMap((t,i)=>isGap(t)?[[i,gapDisplacement(i,tracks,detections,adjacentPairs,time)] as const]:[]));
 const matches:Edge[]=[],uncertainTracks=new Set<number>(),uncertainDetections=new Set<number>(),ambiguities:Edge[]=[];
 for(const lane of new Set([...tracks,...detections].map(x=>x.lane))){
  const a=tracks.flatMap((t,i)=>t.lane===lane?[i]:[]),b=detections.flatMap((d,i)=>d.lane===lane?[i]:[]);
  if(!a.length||!b.length)continue;
  const hypotheses=alternatives.length>1?alternatives.map(d=>new Map(displacements).set(d.fromSeconds,d)):[displacements];
  const search=hypotheses.map(m=>a.map(i=>b.map(j=>compatible(tracks[i],detections[j],time,spacing,m))));
  const tables=hypotheses.map((m,k)=>a.map((i,ii)=>b.map((j,jj)=>{
   if(!gapMotion.has(i))return search[k][ii][jj];
   const measured=gapMotion.get(i);
   return !!measured&&compatible(tracks[i],detections[j],time,spacing,new Map([[measured.fromSeconds,measured]]));
  })));
  const forcedByModel=tables.map(uniqueEdges);
  const forced=forcedByModel[0].filter(([i,j])=>forcedByModel.every(edges=>edges.some(([a,b])=>a===i&&b===j)));
  const edges=a.map((_,i)=>b.map((_,j)=>tables.some(edges=>edges[i][j])||search.some(edges=>edges[i][j])));
  for(const [i,j]of forced){
   matches.push([a[i],b[j]]);
   const measured=gapMotion.get(a[i]);
   if(measured)gapConnections.push({track:a[i],detection:b[j],...measured.proof});
  }
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
 return {gapConnections,translationAlternatives:alternatives,cadenceWarnings,matches,ambiguousTracks:[...uncertainTracks],ambiguousDetections:[...uncertainDetections],ambiguities,measuredDisplacement:measured,step};
}
