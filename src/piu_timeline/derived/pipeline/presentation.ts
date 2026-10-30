/** Prepared observations -> interpretation -> policy -> ranges/audit -> report data. */
import {present} from '../hold_presentation.ts';
import {models} from '../scroll.ts';
import {interpret as effects} from '../effects.ts';
import {policyProjection} from '../evidence.ts';
import {counterFrameRanges, timingRanges} from '../ranges.ts';
import {continuity} from '../visibility.ts';
import {exclusions, recognition} from '../diagnostics.ts';
import * as inputs from './inputs.ts';
import {Store, fingerprint, implementation, atomicJSON} from './store.ts';
import type {RecordData} from '../types.ts';
import {resolve, isAbsolute} from 'node:path';
import {existsSync, readFileSync, statSync} from 'node:fs';
import {parseData} from '../json.ts';

import {artifact,type Evidence} from '../stages/contracts.ts';
import {calculationView,type InspectionArtifact,type InterpretationArtifact,type PresentationInput,type ViewArtifact,type ViewStage} from './contracts.ts';
import {result,applyResult,materialize} from './composition.ts';
export {input} from './contracts.ts';
export {materialize} from './composition.ts';
export type {PresentationInput} from './contracts.ts';
const composition = readFileSync(new URL('./presentation.ts', import.meta.url), 'utf8');
const producer = (module: string) => fingerprint({composition, contracts: implementation(new URL('./contracts.ts', import.meta.url)),
  compositionRules: implementation(new URL('./composition.ts', import.meta.url)), inputs: implementation(new URL('./inputs.ts', import.meta.url)),
  algorithm: implementation(new URL(`../${module}.ts`, import.meta.url))});
const modules = {'hold-view': 'hold_presentation', 'motion-effects': 'scroll', 'effect-view': 'effects', 'policy-view': 'evidence',
  'timing-ranges': 'ranges', visibility: 'visibility', diagnostics: 'diagnostics'};
export function current(directory: string): boolean {
  const path = resolve(directory, 'derived-stages/manifest.json');
  if (!existsSync(path)) return false;
  const manifest = parseData(readFileSync(path, 'utf8'));
  if (manifest.schema !== 1 || !Array.isArray(manifest.stages) || manifest.stages.length !== Object.keys(modules).length) return false;
  for (const [name, signature] of Object.entries(manifest.source_artifacts ?? {})) {
    const source = resolve(directory, name);
    if (isAbsolute(name) || name.split(/[\\/]/).includes('..')) throw new Error('Invalid source artifact reference');
    const stat = existsSync(source) ? statSync(source, {bigint: true}) : null;
    if (fingerprint(stat ? [stat.size, stat.mtimeNs] : null) !== fingerprint(signature)) return false;
  }
  const seen = new Set();
  for (const record of manifest.stages) {
    if (!Object.hasOwn(modules, record.stage) || seen.has(record.stage) || record.producer !== producer(modules[record.stage])) return false;
    seen.add(record.stage);
    const artifact = resolve(directory, 'derived-stages', `${record.stage}.json`);
    if (!existsSync(artifact)) return false;
    const saved = parseData(readFileSync(artifact, 'utf8'));
    if (saved.schema !== 1 || saved.stage !== record.stage || saved.producer !== record.producer || saved.input_fingerprint !== record.input || saved.output_fingerprint !== record.output || fingerprint(saved.output) !== record.output) {
      throw new Error(`Corrupt derived stage artifact: ${record.stage}`);
    }
  }
  return true;
}
function validate(input: PresentationInput): void {
  if (input.schema !== 2 || !input.source || !input.observations || !Array.isArray(input.observations.frames) || !Array.isArray(input.observations.visibility_frames) || !Array.isArray(input.observations.occluders) ||
    typeof input.observations.native_body_risk_available !== 'boolean' || !input.observations.pre_hold_proofs) throw new Error('Invalid prepared presentation input');
  let last = -Infinity;
  for (const frame of input.observations.frames) {
    if (!Number.isFinite(frame.playback_seconds) || !Number.isFinite(frame.source_pts_seconds) || frame.playback_seconds <= last) throw new Error('Invalid presentation observation timeline');
    last = frame.playback_seconds;
  }
  const visible = input.observations.visibility_frames;
  if (visible.length !== input.observations.frames.length || visible.some((f, i) => !Number.isFinite(f.playback_seconds) || !Number.isFinite(f.source_pts_seconds) ||
    Math.abs(f.playback_seconds - input.observations.frames[i].playback_seconds) > 1e-6 || Math.abs(f.source_pts_seconds - input.observations.frames[i].source_pts_seconds) > 1e-6)) {
    throw new Error('Presentation channels have different source timelines');
  }
}
export function preview(input:PresentationInput,directory?:string):InterpretationArtifact{
 const stages:ViewArtifact[]=[];interpreted(input,new Store(directory),stages);return artifact('interpretation',{stages});
}
function interpreted(input: PresentationInput, store:Store, stages:ViewArtifact[]): RecordData {
  validate(input);
  const base=calculationView(input.source);
  const source = inputs.interpretation(base, input.observations.native_body_risk_available);
  const request = {source, proofs: input.observations.pre_hold_proofs};
  const patch = store.run('hold-view', producer('hold_presentation'), request, () => {
    const copy = structuredClone(request);
    return result('hold-view',base,inputs.pick(present(copy.source, copy.proofs), inputs.viewFields));
  });
  stages.push(patch);
  const data = applyResult(base,patch), policy = {chart_policy: data.chart_policy ?? {}};
  const motion = store.run('motion-effects', producer('scroll'), policy, () => result('motion-effects',data,{scroll_pause_model: models(policy, 'pause'), scroll_speed_model: models(policy, 'speed')}));
  stages.push(motion);return applyResult(data,motion);
}

export function prepare(input: PresentationInput, directory?: string):InspectionArtifact {
  const store = new Store(directory);
  const stages:ViewArtifact[]=[];
  let data = interpreted(input,store,stages);
  const measured = input.observations.configured_processing;
  if (measured) {
    if (fingerprint(measured.input) !== fingerprint(inputs.processing({...data,...inputs.pick(input.source.metadata,['media','game_roi'])}))) throw new Error('Configured processing evidence belongs to different interpretation inputs');
    const configured=result('configured-processing',data,{visual_channels:{processing:measured.output}});
    stages.push(configured);data=applyResult(data,configured);
  }
  const effectInput = {...inputs.evidence(data), object_interpretation: data.object_interpretation,
    visual_channels: {...inputs.evidence(data).visual_channels, ...(data.visual_channels?.processing ? {processing: inputs.processingChannel(data)} : {})}};
  const effectPatch = store.run('effect-view', producer('effects'), effectInput, () => result('effect-view',data,inputs.pick(effects(structuredClone(effectInput)),
    ['combo_events', 'matches', 'coverage', 'conflicted_matches', 'association_view_format', 'object_interpretation', 'chart_policy', 'visual_channels'])));
  stages.push(effectPatch);data=applyResult(data,effectPatch);
  const policyInput = inputs.evidence(data);
  const projected = store.run('policy-view', producer('evidence'), policyInput, () => result('policy-view',data,inputs.pick(policyProjection(structuredClone(policyInput)),['matches','miss_candidates','hold_analysis','coverage'])));
  stages.push(projected);data=applyResult(data,projected);
  const rangeInput = {data: inputs.evidence(data), frames: input.observations.frames.map(f => inputs.pick(f, ['playback_seconds', 'source_pts_seconds', 'combo', 'combo_confidence']))};
  const ranges = store.run('timing-ranges', producer('ranges'), rangeInput, () => {
    const initial = timingRanges(rangeInput.data);
    return result('timing-ranges',data,{timing_ranges:initial.counts.unknown && rangeInput.frames.length ? timingRanges({...rangeInput.data, counter_frame_events: counterFrameRanges(rangeInput.frames)}) : initial});
  });
  const visibilityInput = {data: inputs.visibility(data), frames: input.observations.visibility_frames, occluders: input.observations.occluders};
  const visible = store.run('visibility', producer('visibility'), visibilityInput, () => result('visibility',data,{visibility_diagnostics:continuity(visibilityInput.data, [...visibilityInput.frames], [...visibilityInput.occluders])}));
  stages.push(ranges,visible);data=applyResult(applyResult(data,ranges),visible);
  const diagnosticInput = {native: {notes: calculationView(input.source).notes ?? []}, projected: inputs.pick(data, ['notes', 'hold_analysis', 'chart_policy']),
    data: inputs.recognition(data), ranges:data.timing_ranges};
  const diagnostics = store.run('diagnostics', producer('diagnostics'), diagnosticInput, () => result('diagnostics',data,{
    exclusion_diagnostics: exclusions(diagnosticInput.native, diagnosticInput.projected), recognition_diagnostics: recognition(diagnosticInput.data, diagnosticInput.ranges)}));
  if (directory) atomicJSON(resolve(directory, 'derived-stages/manifest.json'), {schema: 1, source_artifacts: input.observations.source_artifacts ?? {}, stages: store.records});
  stages.push(diagnostics);return artifact('inspection',{stages});
}
