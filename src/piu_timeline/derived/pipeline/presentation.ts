/** Prepare inspection artifacts. Composition and HTML rendering are separate entry points. */
import {resolve, isAbsolute} from 'node:path';
import {existsSync, readFileSync, statSync} from 'node:fs';
import {parseData} from '../json.ts';
import {present} from '../hold_presentation.ts';
import {models} from '../scroll.ts';
import {interpret as effects} from '../effects.ts';
import {policyProjection} from '../evidence.ts';
import {counterFrameRanges, timingRanges} from '../ranges.ts';
import {continuity} from '../visibility.ts';
import {exclusions, recognition} from '../diagnostics.ts';
import {boundArtifact} from '../stages/contracts.ts';
import type {RecordData} from '../types.ts';
import * as inputs from './inputs.ts';
import {Store, fingerprint, implementation, atomicJSON} from './store.ts';
import {
  calculationView, type InspectionArtifact, type InterpretationArtifact,
  type PresentationInput, type ViewArtifact,
} from './contracts.ts';
import {result, applyResult, materialize} from './composition.ts';
import {input as captureInput}from './contracts.ts';
export {input} from './contracts.ts';
export {materialize} from './composition.ts';
export type {PresentationInput} from './contracts.ts';

/** Compose saved artifacts independently; do not join both documents in one wire request. */
export function materializeFiles(inputPath:string,resultPath:string,outputPath:string):void{
  const input=parseData(readFileSync(inputPath,'utf8')),result=parseData(readFileSync(resultPath,'utf8'));
  atomicJSON(outputPath,materialize(input,result));
}

/** Acquisition persists independent pieces once; the worker receives paths only. */
export function inputFiles(sourcePath:string,nativePath:string,artifactRoot:string,outputPath:string):void{
 atomicJSON(outputPath,captureInput(parseData(readFileSync(sourcePath,'utf8')),parseData(readFileSync(nativePath,'utf8')),artifactRoot));
}
export function previewFile(inputPath:string,directory:string,outputPath:string):void{
 atomicJSON(outputPath,preview(parseData(readFileSync(inputPath,'utf8')),directory));
}

/** Consume the persisted request; the process boundary carries paths only. */
export function prepareFile(inputPath:string,directory:string,outputPath:string):void{
 atomicJSON(outputPath,prepare(parseData(readFileSync(inputPath,'utf8')),directory));
}

const composition = readFileSync(new URL('./presentation.ts', import.meta.url), 'utf8');
const modules = {
  'hold-view': 'hold_presentation', 'motion-effects': 'scroll', 'effect-view': 'effects',
  'policy-view': 'evidence', 'timing-ranges': 'ranges', visibility: 'visibility', diagnostics: 'diagnostics',
};
const producer = (module: string) => fingerprint({
  composition,
  contracts: implementation(new URL('./contracts.ts', import.meta.url)),
  compositionRules: implementation(new URL('./composition.ts', import.meta.url)),
  inputs: implementation(new URL('./inputs.ts', import.meta.url)),
  algorithm: implementation(new URL(`../${module}.ts`, import.meta.url)),
});

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
    const intact = saved.schema === 1 && saved.stage === record.stage && saved.producer === record.producer &&
      saved.input_fingerprint === record.input && saved.output_fingerprint === record.output && fingerprint(saved.output) === record.output;
    if (!intact) throw new Error(`Corrupt derived stage artifact: ${record.stage}`);
  }
  return true;
}

function validate(input: PresentationInput): void {
  if (input.schema !== 2 || !input.source || !input.observations || !Array.isArray(input.observations.frames) ||
      !Array.isArray(input.observations.visibility_frames) || !Array.isArray(input.observations.occluders) ||
      typeof input.observations.native_body_risk_available !== 'boolean' || !input.observations.pre_hold_proofs) {
    throw new Error('Invalid prepared presentation input');
  }
  let last = -Infinity;
  for (const frame of input.observations.frames) {
    if (!Number.isFinite(frame.playback_seconds) || !Number.isFinite(frame.source_pts_seconds) || frame.playback_seconds <= last) {
      throw new Error('Invalid presentation observation timeline');
    }
    last = frame.playback_seconds;
  }
  const visible = input.observations.visibility_frames;
  const sameTimeline = visible.length === input.observations.frames.length && visible.every((frame, i) =>
    Number.isFinite(frame.playback_seconds) && Number.isFinite(frame.source_pts_seconds) &&
    Math.abs(frame.playback_seconds - input.observations.frames[i].playback_seconds) <= 1e-6 &&
    Math.abs(frame.source_pts_seconds - input.observations.frames[i].source_pts_seconds) <= 1e-6);
  if (!sameTimeline) throw new Error('Presentation channels have different source timelines');
}

function interpret(input: PresentationInput, store: Store): {view: RecordData; stages: ViewArtifact[]} {
  validate(input);
  const base = calculationView(input.source);
  const request = {
    source: inputs.interpretation(base, input.observations.native_body_risk_available),
    proofs: input.observations.pre_hold_proofs,
  };
  const hold = store.run('hold-view', producer('hold_presentation'), request, () => {
    const copy = structuredClone(request);
    return result('hold-view', base, inputs.pick(present(copy.source, copy.proofs), inputs.viewFields));
  });
  const view = applyResult(base, hold);
  const policy = {chart_policy: view.chart_policy ?? {}};
  const motion = store.run('motion-effects', producer('scroll'), policy, () => result('motion-effects', view, {
    scroll_pause_model: models(policy, 'pause'), scroll_speed_model: models(policy, 'speed'),
  }));
  return {view: applyResult(view, motion), stages: [hold, motion]};
}

/** Native preparation uses this partial result before measuring configured motion. */
export function preview(input: PresentationInput, directory?: string): InterpretationArtifact {
  const {stages} = interpret(input, new Store(directory));
  return boundArtifact('interpretation', input, {stages}, input.artifact_root);
}

export function prepare(input: PresentationInput, directory?: string): InspectionArtifact {
  const store = new Store(directory);
  const interpretation = interpret(input, store);
  const stages = interpretation.stages;
  let view = interpretation.view;

  // Optional native measurement: verify its prepared inputs; this consumer never reads pixels.
  const measured = input.observations.configured_processing;
  if (measured) {
    const nativeContext = {...view, ...inputs.pick(input.source.metadata, ['media', 'game_roi'])};
    if (fingerprint(measured.input) !== fingerprint(inputs.processing(nativeContext))) {
      throw new Error('Configured processing evidence belongs to different interpretation inputs');
    }
    const configured = result('configured-processing', view, {visual_channels: {processing: measured.output}});
    stages.push(configured);
    view = applyResult(view, configured);
  }

  const evidence = inputs.evidence(view);
  const effectInput = {
    ...evidence, object_interpretation: view.object_interpretation,
    visual_channels: {...evidence.visual_channels,
      ...(view.visual_channels?.processing ? {processing: inputs.processingChannel(view)} : {})},
  };
  const effect = store.run('effect-view', producer('effects'), effectInput, () => result('effect-view', view,
    inputs.pick(effects(structuredClone(effectInput)), [
      'combo_events', 'matches', 'coverage', 'conflicted_matches', 'association_view_format',
      'object_interpretation', 'chart_policy', 'visual_channels',
    ])));
  stages.push(effect);
  view = applyResult(view, effect);

  const policyInput = inputs.evidence(view);
  const policy = store.run('policy-view', producer('evidence'), policyInput, () => result('policy-view', view,
    inputs.pick(policyProjection(structuredClone(policyInput)), ['matches', 'miss_candidates', 'hold_analysis', 'coverage'])));
  stages.push(policy);
  view = applyResult(view, policy);

  const rangeInput = {
    data: inputs.evidence(view),
    frames: input.observations.frames.map(frame => inputs.pick(frame, ['playback_seconds', 'source_pts_seconds', 'combo', 'combo_confidence'])),
  };
  const ranges = store.run('timing-ranges', producer('ranges'), rangeInput, () => {
    let timing = timingRanges(rangeInput.data);
    if (timing.counts.unknown && rangeInput.frames.length) {
      timing = timingRanges({...rangeInput.data, counter_frame_events: counterFrameRanges(rangeInput.frames)});
    }
    return result('timing-ranges', view, {timing_ranges: timing});
  });

  const visibilityInput = {data: inputs.visibility(view), frames: input.observations.visibility_frames, occluders: input.observations.occluders};
  const visible = store.run('visibility', producer('visibility'), visibilityInput, () => result('visibility', view, {
    visibility_diagnostics: continuity(visibilityInput.data, [...visibilityInput.frames], [...visibilityInput.occluders]),
  }));
  stages.push(ranges, visible);
  view = applyResult(applyResult(view, ranges), visible);

  const diagnosticInput = {
    native: {notes: calculationView(input.source).notes ?? []},
    projected: inputs.pick(view, ['notes', 'hold_analysis', 'chart_policy']),
    data: inputs.recognition(view), ranges: view.timing_ranges,
  };
  const diagnostics = store.run('diagnostics', producer('diagnostics'), diagnosticInput, () => result('diagnostics', view, {
    exclusion_diagnostics: exclusions(diagnosticInput.native, diagnosticInput.projected),
    recognition_diagnostics: recognition(diagnosticInput.data, diagnosticInput.ranges),
  }));
  stages.push(diagnostics);
  if (directory) {
    atomicJSON(resolve(directory, 'derived-stages/manifest.json'), {
      schema: 1, source_artifacts: input.observations.source_artifacts ?? {}, stages: store.records,
    });
  }
  return boundArtifact('inspection', input, {stages}, input.artifact_root);
}
