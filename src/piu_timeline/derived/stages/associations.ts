/** Input associations consume timing and visual evidence; they never return coordinate edits. */
import {associate} from '../association.ts';
import {mergeJudgments} from '../labels.ts';
import {artifact,requireArtifact,type Artifact,type Evidence,type Immutable} from './contracts.ts';
import type {RecordData} from '../types.ts';
export interface TimingNote {lane:number;status:string;target_seconds:number|null;prediction_uncertainty_seconds?:number;reason?:string|null}
export interface CounterRequest {
 schema:1;notes:readonly TimingNote[];events:readonly Evidence[];display_delay_seconds:number;
 unsupported_intervals:readonly {start_seconds:number;end_seconds:number}[];constraints?:Readonly<Record<string,number[]>>|null;
}
export interface CounterResult {combo_events:readonly Evidence[];matches:readonly Evidence[];deferred_matches:readonly Evidence[];coverage:Evidence;excluded_notes:Evidence}
export type CounterArtifact=Artifact<'counter-associations',CounterResult>;
export function counters(input:CounterRequest):CounterArtifact{
 if(input.schema!==1||!Array.isArray(input.notes)||!Array.isArray(input.events)||!Number.isFinite(input.display_delay_seconds))throw new Error('Invalid counter association input');
 const fields=['lane','status','target_seconds','prediction_uncertainty_seconds','reason'];
 if(input.notes.some(n=>Object.keys(n).some(k=>!fields.includes(k))))throw new Error('Counter association received fields outside timing contract');
 const events=structuredClone(input.events) as RecordData[],notes=structuredClone(input.notes) as TimingNote[];
 const candidates=associate(notes,events,.045,input.display_delay_seconds,input.constraints as Record<string,number[]>),matches=[],deferred=[];
 for(const match of candidates){
  if(input.unsupported_intervals.some(interval=>match.combo_upper_seconds>=interval.start_seconds-.1&&match.combo_lower_seconds<=interval.end_seconds+.1)){
   Object.assign(events[match.combo_event],{status:'excluded',reason:'possible_hold_or_dense_stack'});deferred.push({...match,deferred_reason:'possible_hold_or_dense_stack'});
  }else matches.push(match);
 }
 const excluded:Record<string,number>={};for(const n of input.notes as readonly (TimingNote&{reason?:string})[])if(n.status==='excluded')excluded[String(n.reason??null)]=(excluded[String(n.reason??null)]??0)+1;
 return artifact('counter-associations',{combo_events:events,matches,deferred_matches:deferred,excluded_notes:excluded,
  coverage:{visible_note_heads:notes.filter(n=>n.status==='estimated').length,timed_note_heads:matches.length,
   matched_combo_updates:new Set(matches.map(m=>m.combo_event)).size,observed_combo_updates:events.filter(e=>e.delta>0).length}});
}
export interface JudgmentSource {
 notes:readonly TimingNote[];matches?:readonly Evidence[];conflicted_matches?:readonly Evidence[];
 combo_events?:readonly Evidence[];coverage?:Evidence;display_delay_correction_ms?:number;
 unsupported_intervals?:readonly Evidence[];
}
export interface JudgmentRequest {schema:1;source:Artifact<'judgment-input',JudgmentSource>;events:readonly Evidence[];observations:readonly Evidence[]}
const judgmentInputs=['notes','matches','conflicted_matches','combo_events','coverage','display_delay_correction_ms','unsupported_intervals'];
const timingFields=['lane','status','target_seconds','prediction_uncertainty_seconds','reason'];
const judgmentFields=['matches','conflicted_matches','judgment_events','miss_candidates','coverage','counter_judgment_labels'] as const;
export type JudgmentArtifact=Artifact<'judgment-associations',Partial<Record<typeof judgmentFields[number],unknown>>>;
export function judgmentInput(data:RecordData,events:RecordData[],observations:RecordData[]):JudgmentRequest{
 const source=Object.fromEntries(judgmentInputs.filter(k=>Object.hasOwn(data,k)).map(k=>[k,k==='notes'?data.notes.map(n=>Object.fromEntries(timingFields.filter(f=>Object.hasOwn(n,f)).map(f=>[f,n[f]]))):data[k]])) as unknown as JudgmentSource;
 return {schema:1,source:artifact('judgment-input',source),events,observations};
}
export function judgments(request:JudgmentRequest):JudgmentArtifact{
 if(request.schema!==1)throw new Error('Invalid judgment association input');requireArtifact(request.source,'judgment-input');
 if(Object.keys(request.source.data).some(k=>!judgmentInputs.includes(k))||request.source.data.notes.some(n=>Object.keys(n).some(k=>!timingFields.includes(k))))throw new Error('Foreign fields in judgment input');
 const data=structuredClone(request.source.data) as RecordData;
 const result=mergeJudgments(data,structuredClone(request.events) as RecordData[],structuredClone(request.observations) as RecordData[]);
 return artifact('judgment-associations',Object.fromEntries(judgmentFields.filter(k=>Object.hasOwn(result,k)).map(k=>[k,result[k]])));
}
