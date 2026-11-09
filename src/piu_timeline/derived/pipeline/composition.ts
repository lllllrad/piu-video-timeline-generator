/** Explicit read-model composition. Producer artifacts are never rewritten. */
import {artifact, requireArtifact, requireInput} from '../stages/contracts.ts';
import {changes, apply, type NotePatch} from '../stages/notes.ts';
import {
  calculationView, interpretationOrder, inspectionOrder, type PresentationInput,
  type ViewArtifact, type ViewStage, type InspectionArtifact, type InterpretationArtifact,
} from './contracts.ts';
import type {RecordData} from '../types.ts';

const holdNoteFields = [
  'status', 'reason', 'target_seconds', 'prediction_uncertainty_seconds', 'type_status', 'type_evidence',
  'type_unknown_reasons', 'note_type', 'hold_cap_role', 'observed_hold_head', 'hold_id', 'input_requirement',
  'requires_head_press', 'observed_hold_id', 'observed_note_type', 'chart_timing_status', 'target_timing_basis', 'geometry_native_range', 'geometry_source_failure',
];
const ownedOutputs = {
  'configured-processing': ['visual_channels'],
  'hold-view': ['matches', 'limitations', 'excluded_notes', 'miss_candidates', 'combo_events', 'judgment_events',
    'hold_tick_ambiguous_notes', 'recovered_pre_hold_notes', 'recovered_dense_notes', 'recovered_lane_supported_notes',
    'recovered_bounded_target_notes', 'hold_analysis', 'coverage', 'note_type_diagnostics', 'conflicted_matches', 'association_view_format'],
  'motion-effects': ['scroll_pause_model', 'scroll_speed_model'],
  'effect-view': ['combo_events', 'matches', 'coverage', 'conflicted_matches', 'association_view_format',
    'object_interpretation', 'chart_policy', 'visual_channels'],
  'policy-view': ['matches', 'miss_candidates', 'hold_analysis', 'coverage'],
  'timing-ranges': ['timing_ranges'],
  visibility: ['visibility_diagnostics'],
  diagnostics: ['exclusion_diagnostics', 'recognition_diagnostics'],
} as const;

export function result(stage: ViewStage, before: RecordData, patch: RecordData): ViewArtifact {
  const allowed = ownedOutputs[stage] as readonly string[];
  if (Object.keys(patch).some(key => key !== 'notes' && !allowed.includes(key))) {
    throw new Error(`Unowned output from ${stage}`);
  }
  const existingCount = (before.notes ?? []).length;
  const updates = patch.notes
    ? changes(before.notes ?? [], patch.notes.slice(0, existingCount), stage === 'hold-view' ? holdNoteFields : [])
    : [];
  const derivedNotes = patch.notes?.slice(existingCount) ?? [];
  if (derivedNotes.length && stage !== 'hold-view') throw new Error(`Unexpected chart objects from ${stage}`);
  const fields = Object.fromEntries(Object.entries(patch).filter(([key]) => key !== 'notes'));
  return artifact(stage, {...fields, note_updates: updates, derived_notes: derivedNotes});
}

/** Compact effect views overlay interpretation fields while retaining measured samples. */
function mergeProcessingNotes(original: RecordData, projected: RecordData): RecordData {
  const byNote = new Map((original?.notes ?? []).map(note => [note.note, note]));
  return {
    ...projected,
    notes: projected.notes.map(note => {
      const {sample_count, ...view} = note;
      return {...byNote.get(note.note) as RecordData, ...view};
    }),
  };
}

function mergeChannels(before: RecordData, patch: RecordData, stage: ViewStage): RecordData | undefined {
  // An effect view cannot invent measured channels. A prepared native result can create one.
  if (!before && stage !== 'configured-processing') return undefined;
  const channels = {...before};
  for (const [name, value] of Object.entries(patch)) {
    if (value === undefined) continue;
    let channel = {...before?.[name], ...value as RecordData};
    if (stage === 'effect-view' && name === 'processing' && channel.notes) {
      channel = mergeProcessingNotes(before?.processing, channel);
    }
    channels[name] = channel;
  }
  return channels;
}

export function applyResult(before: RecordData, value: ViewArtifact): RecordData {
  requireArtifact(value, value.stage);
  if (!Object.hasOwn(ownedOutputs, value.stage)) throw new Error('Unknown inspection stage');
  const {note_updates, derived_notes, ...patch} = value.data;
  if (Object.keys(patch).some(key => !(ownedOutputs[value.stage] as readonly string[]).includes(key))) {
    throw new Error(`Unowned output from ${value.stage}`);
  }
  const notes = apply(before.notes ?? [], note_updates as unknown as NotePatch[], value.stage === 'hold-view' ? holdNoteFields : []);
  if ((derived_notes as unknown[]).length && value.stage !== 'hold-view') throw new Error('Foreign derived chart objects');

  const owned = structuredClone(patch) as RecordData;
  if (value.stage === 'policy-view' && owned.hold_analysis) {
    owned.hold_analysis = {...before.hold_analysis, ...owned.hold_analysis};
  }
  if (owned.visual_channels) {
    const channels = mergeChannels(before.visual_channels, owned.visual_channels, value.stage);
    if (channels) owned.visual_channels = channels;
    else delete owned.visual_channels;
  }
  return {...before, ...owned, notes: [...notes, ...structuredClone(derived_notes as unknown[])]};
}

function validateOrder(request: PresentationInput, value: InspectionArtifact | InterpretationArtifact): void {
  const expected = value.stage === 'interpretation'
    ? interpretationOrder
    : inspectionOrder.filter(stage => stage !== 'configured-processing' || request.observations.configured_processing);
  if (value.data.stages.length !== expected.length || value.data.stages.some((stage, i) => stage.stage !== expected[i])) {
    throw new Error('Incomplete or out-of-order inspection stages');
  }
}

export function materialize(request: PresentationInput, value: InspectionArtifact | InterpretationArtifact): RecordData {
  requireArtifact(value, value.stage);
  if (value.stage !== 'inspection' && value.stage !== 'interpretation') throw new Error('Expected an inspection or interpretation result');
  requireInput(value, request);
  validateOrder(request, value);
  let view = calculationView(request.source);
  for (const stage of value.data.stages) view = applyResult(view, stage);
  return {...structuredClone(request.source.metadata), ...view};
}
