/** Resolve provisional identity edges from both observed approaches, never target/input times. */
import {affineDomain}from '../coordinates/phase_clock.ts';
import {sameBasis}from '../coordinates/measurements.ts';
import type {RecordData}from '../types.ts';

import {referenceMotion,type IdentityDecision as State}from './source_motion.ts';
function evidence(first:RecordData,second:RecordData):State{
 const before=first.observations.slice(-12),after=second.observations.slice(0,12);
 const roles=new Set([...before,...after].map(o=>o.capRole).filter(Boolean));
 if(roles.size>1)return {status:'refuted',reason:'different_observed_cap_roles'};
 if(!before.length||!after.length||before.at(-1).time>=after[0].time)
  return {status:'refuted',reason:'coobserved_or_reversed_fragments'};
 const observations=[...before,...after],centers=observations.every(o=>o.center);
 const positions=centers?observations.map(o=>o.center):observations.map(o=>o.anchor);
 if(!positions.every(p=>p&&sameBasis(p.basis,positions[0].basis)))return {status:'pending',reason:'no_common_coordinate_basis'};
 if(observations.some(o=>!Number.isFinite(o.sourcePtsSeconds))||observations.slice(1).some((o,i)=>
  o.time<=observations[i].time||o.sourcePtsSeconds<=observations[i].sourcePtsSeconds||
  Math.abs((o.time-observations[i].time)-(o.sourcePtsSeconds-observations[i].sourcePtsSeconds))>1e-6))
  return {status:'pending',reason:'missing_or_discontinuous_source_identity'};
 if(before.length<2||after.length<2||Math.max(before.length,after.length)<4||
  observations.length<8||observations.at(-1).time-observations[0].time<.065)
  return {status:'pending',reason:'insufficient_past_or_future_observations'};
 if(observations.slice(1).some((o,i)=>o.time-observations[i].time>.05+1e-6))
  return {status:'pending',reason:'unobserved_capture_interval'};
 const count=before.length,points=observations.map((o,i)=>[o.time,-positions[i].yPixels]);
 // Capture phase is temporal uncertainty measured *within* independently linked
 // fragments. The proposed gap never supplies its own error allowance.
 const steps=points.slice(1).flatMap((p,i)=>i+1===count?[]:[Math.abs(p[1]-points[i][1])]);
 const capture=Math.max(...steps),endpoint=Math.max(...positions.map(p=>p.uncertaintyPixels));
 const domain=affineDomain(points,capture+endpoint);
 if(!domain)return {status:'refuted',reason:'past_and_future_motion_incompatible'};
 return {status:'supported',reason:'past_and_future_native_approaches',proof:{
  method:'deferred_native_approaches',coordinate_basis:positions[0].basis,
  observed_cap_role:[...roles][0]??null,observed_render_step_pixels:capture,endpoint_uncertainty_pixels:endpoint,
  phase_error_pixels:capture+endpoint,clock_domain:domain,
  source_pts_seconds:observations.map(o=>o.sourcePtsSeconds),
  references:observations.map((o,i)=>({time:o.time,source_pts_seconds:o.sourcePtsSeconds,y_pixels:positions[i].yPixels})),
  predecessor_end_seconds:before.at(-1).time,successor_start_seconds:after[0].time}};
}

/** Only mutually unique supported survivors may join. Pending alternatives block joining. */
export function resolve(source:RecordData[],proposals:RecordData[],timeline:RecordData[]=[],spacing=40):RecordData[]{
 const external=referenceMotion(source,timeline,spacing);
 const byId=new Map(source.map((s,i)=>[s.id,i]));
 if(byId.size!==source.length)throw Error('Deferred tracking requires unique fragment identities');
 const parent=source.map((_,i)=>i),members=source.map((_,i)=>[i]),proofs=source.map(()=>[] as RecordData[]);
 const root=(i:number):number=>parent[i]===i?i:(parent[i]=root(parent[i]));
 const edges=[...new Map(proposals.map(e=>{
  const a=byId.get(e.from),b=byId.get(e.to);
  if(a===undefined||b===undefined||source[a].lane!==source[b].lane||!Number.isFinite(e.time))throw Error('Invalid deferred tracking edge');
  return [`${a},${b}`,{a,b,time:e.time}];
 })).values()];
 const combined=(i:number)=>({lane:source[i].lane,observations:members[i].flatMap(j=>source[j].observations).sort((a,b)=>a.time-b.time)});
 for(let pass=0;pass<source.length;pass++){
  const states=[...new Map(edges.flatMap(e=>{
   const a=root(e.a),b=root(e.b);
   if(a===b)return [];
   const before=combined(a),after=combined(b),own=evidence(before,after),peers=external(before,after),
    proof=own.status==='refuted'?own:peers.status==='refuted'?peers:own.status==='supported'?own:peers;
   return [[`${a},${b}`,{a,b,time:e.time,...proof}]];
  })).values()] as (State&{a:number;b:number;time:number})[];
  const outgoing=new Map<number,number>(),incoming=new Map<number,number>(),incident=new Map<number,typeof states>();
  for(const state of states){
   for(const id of new Set([state.a,state.b])){
    if(!incident.has(id))incident.set(id,[]);incident.get(id).push(state);
   }
   if(state.status==='refuted')continue;
   outgoing.set(state.a,(outgoing.get(state.a)??0)+1);incoming.set(state.b,(incoming.get(state.b)??0)+1);
  }
  const accepted=states.filter(s=>s.status==='supported'&&outgoing.get(s.a)===1&&incoming.get(s.b)===1);
  if(!accepted.length)break;
  let changed=false;
  for(const edge of accepted){
   if(root(edge.a)!==edge.a||root(edge.b)!==edge.b)continue;
   const alternatives=[...new Set([...(incident.get(edge.a)??[]),...(incident.get(edge.b)??[])])]
    .filter(s=>s.a===edge.a||s.b===edge.b).map(s=>({
    predecessor_fragments:members[s.a].map(i=>source[i].id),successor_fragments:members[s.b].map(i=>source[i].id),status:s.status,reason:s.reason}));
   parent[edge.b]=edge.a;members[edge.a].push(...members[edge.b]);
   proofs[edge.a].push(...proofs[edge.b],{...edge.proof,decision_seconds:edge.time,alternatives});changed=true;
  }
  if(!changed)break;
 }
 return source.flatMap((_,i)=>root(i)===i?[{indices:members[i].sort((a,b)=>a-b),connections:proofs[i],
  resolved_times:proofs[i].map(p=>p.decision_seconds)}]:[]);
}
