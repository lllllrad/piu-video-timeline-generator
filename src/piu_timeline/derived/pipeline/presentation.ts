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

export interface PresentationInput {
  schema: 1;
  data: RecordData;
  observations: {
    frames: RecordData[];
    visibility_frames: RecordData[];
    occluders: RecordData[];
    native_body_risk_available: boolean;
    pre_hold_proofs: Record<string, RecordData>;
    configured_processing?: {input: RecordData; output: RecordData};
    source_artifacts?: Record<string, [number, number | bigint] | null>;
  };
}
const composition = readFileSync(new URL('./presentation.ts', import.meta.url), 'utf8');
const producer = (module: string) => fingerprint({composition, inputs: implementation(new URL('./inputs.ts', import.meta.url)),
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
  if (input.schema !== 1 || !input.data || !input.observations || !Array.isArray(input.observations.frames) || !Array.isArray(input.observations.visibility_frames) || !Array.isArray(input.observations.occluders) ||
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
export const preview = (input: PresentationInput, directory?: string): RecordData => interpreted(input, new Store(directory));
export function interpreted(input: PresentationInput, store = new Store()): RecordData {
  validate(input);
  const source = inputs.interpretation(input.data, input.observations.native_body_risk_available);
  const request = {source, proofs: input.observations.pre_hold_proofs};
  const patch = store.run('hold-view', producer('hold_presentation'), request, () => {
    const copy = structuredClone(request);
    return inputs.pick(present(copy.source, copy.proofs), inputs.viewFields);
  });
  const data = {...input.data, ...patch}, policy = {chart_policy: data.chart_policy ?? {}};
  const motion = store.run('motion-effects', producer('scroll'), policy, () => ({scroll_pause_model: models(policy, 'pause'), scroll_speed_model: models(policy, 'speed')}));
  return {...data, ...motion};
}

export function prepare(input: PresentationInput, directory?: string): RecordData {
  const store = new Store(directory);
  let data = interpreted(input, store);
  const measured = input.observations.configured_processing;
  if (measured) {
    if (fingerprint(measured.input) !== fingerprint(inputs.processing(data))) throw new Error('Configured processing evidence belongs to different interpretation inputs');
    data = {...data, visual_channels: {...data.visual_channels, processing: {...data.visual_channels?.processing, ...measured.output}}};
  }
  const effectInput = {...inputs.evidence(data), object_interpretation: data.object_interpretation,
    visual_channels: {...inputs.evidence(data).visual_channels, ...(data.visual_channels?.processing ? {processing: inputs.processingChannel(data)} : {})}};
  const effectPatch = store.run('effect-view', producer('effects'), effectInput, () => inputs.pick(effects(structuredClone(effectInput)),
    ['combo_events', 'matches', 'coverage', 'conflicted_matches', 'association_view_format', 'object_interpretation', 'chart_policy', 'visual_channels']));
  if (!Object.hasOwn(data, 'visual_channels')) delete effectPatch.visual_channels;
  else if (effectPatch.visual_channels) effectPatch.visual_channels = {...data.visual_channels, ...Object.fromEntries(Object.entries(effectPatch.visual_channels)
    .filter(([, v]) => v !== undefined).map(([k, v]) => [k, {...data.visual_channels?.[k], ...v as RecordData}]))};
  if (effectPatch.visual_channels?.processing && data.visual_channels?.processing) {
    const original = new Map<number, RecordData>((data.visual_channels.processing.notes ?? []).map(n => [n.note, n]));
    effectPatch.visual_channels.processing.notes = effectPatch.visual_channels.processing.notes.map(n => {
      const {sample_count, ...patch} = n;
      return {...original.get(n.note), ...patch};
    });
  }
  data = {...data, ...effectPatch};
  const policyInput = inputs.evidence(data);
  const projected = store.run('policy-view', producer('evidence'), policyInput, () => policyProjection(structuredClone(policyInput)));
  if (projected.hold_analysis) projected.hold_analysis = {...data.hold_analysis, ...projected.hold_analysis};
  data = {...data, ...projected};
  const rangeInput = {data: inputs.evidence(data), frames: input.observations.frames.map(f => inputs.pick(f, ['playback_seconds', 'source_pts_seconds', 'combo', 'combo_confidence']))};
  const ranges = store.run('timing-ranges', producer('ranges'), rangeInput, () => {
    const initial = timingRanges(rangeInput.data);
    return initial.counts.unknown && rangeInput.frames.length ? timingRanges({...rangeInput.data, counter_frame_events: counterFrameRanges(rangeInput.frames)}) : initial;
  });
  const visibilityInput = {data: inputs.visibility(data), frames: input.observations.visibility_frames, occluders: input.observations.occluders};
  const visible = store.run('visibility', producer('visibility'), visibilityInput, () => continuity(visibilityInput.data, visibilityInput.frames, visibilityInput.occluders));
  data = {...data, timing_ranges: ranges, visibility_diagnostics: visible};
  const diagnosticInput = {native: {notes: input.data.notes ?? []}, projected: inputs.pick(data, ['notes', 'hold_analysis', 'chart_policy']),
    data: inputs.recognition(data), ranges};
  const diagnostics = store.run('diagnostics', producer('diagnostics'), diagnosticInput, () => ({
    exclusion_diagnostics: exclusions(diagnosticInput.native, diagnosticInput.projected), recognition_diagnostics: recognition(diagnosticInput.data, ranges)}));
  if (directory) atomicJSON(resolve(directory, 'derived-stages/manifest.json'), {schema: 1, source_artifacts: input.observations.source_artifacts ?? {}, stages: store.records});
  return {...data, ...diagnostics};
}
