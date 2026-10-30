/** Inspection input scopes. Passive document metadata never enters inference. */
import {artifact, requireArtifact, type Artifact, type BoundArtifact, type Evidence, type Immutable} from '../stages/contracts.ts';
import type {RecordData} from '../types.ts';

export const scopes = {
  tracks: ['notes', 'layout', 'analysis_width', 'analysis_height', 'head_registration', 'scroll_motion',
    'timing_reconstruction', 'beat_timing', 'start_seconds', 'end_seconds', 'skin_detector'],
  judgments: ['matches', 'conflicted_matches', 'miss_candidates', 'combo_events', 'judgment_events',
    'counter_frame_events', 'counter_judgment_labels', 'display_delay_correction_ms', 'median_frame_interval_seconds',
    'unsupported_intervals', 'coverage', 'excluded_notes', 'limitations', 'deferred_matches', 'association_view_format',
    'hold_tick_ambiguous_notes', 'recovered_pre_hold_notes', 'recovered_dense_notes',
    'recovered_lane_supported_notes', 'recovered_bounded_target_notes'],
  holds: ['hold_analysis', 'note_type_diagnostics', 'skin_role_evidence', 'body_risk_evidence'],
  context: ['chart_policy', 'object_interpretation', 'visual_support', 'scroll_pause_model', 'scroll_speed_model'],
  channels: ['visual_channels'],
} as const;

type Selection<T extends readonly string[]> = {readonly [K in T[number]]?: unknown};
export interface InspectionSource {
  tracks: Artifact<'inspection-tracks', Selection<typeof scopes.tracks>>;
  judgments: Artifact<'inspection-associations', Selection<typeof scopes.judgments>>;
  holds: Artifact<'hold-evidence', Selection<typeof scopes.holds>>;
  context: Artifact<'chart-context', Selection<typeof scopes.context>>;
  channels: Artifact<'visual-channels', Selection<typeof scopes.channels>>;
  metadata: Evidence;
}
const kinds = {
  tracks: 'inspection-tracks', judgments: 'inspection-associations', holds: 'hold-evidence',
  context: 'chart-context', channels: 'visual-channels',
} as const;

/** Acquisition adapter: partition a document once, before any consumer calculation. */
export function capture(data: RecordData): InspectionSource {
  const knownFields = new Set<string>(Object.values(scopes).flat());
  const source = {} as InspectionSource;
  for (const [scope, fields] of Object.entries(scopes)) {
    const selected = Object.fromEntries(fields.filter(key => Object.hasOwn(data, key)).map(key => [key, data[key]]));
    source[scope] = artifact(kinds[scope], selected);
  }
  source.metadata = structuredClone(Object.fromEntries(Object.entries(data).filter(([key]) => !knownFields.has(key))));
  return source;
}

export function calculationView(source: InspectionSource): RecordData {
  const view: RecordData = {};
  for (const [scope, kind] of Object.entries(kinds)) {
    const value = source[scope];
    requireArtifact(value, kind);
    if (Object.keys(value.data).some(key => !scopes[scope].includes(key))) {
      throw new Error(`Foreign fields in ${kind} input`);
    }
    Object.assign(view, structuredClone(value.data));
  }
  return view;
}

export interface CounterFrame {
  playback_seconds: number;
  source_pts_seconds: number;
  combo?: number | null;
  combo_confidence?: number;
}
export interface VisibilityFrame {
  playback_seconds: number;
  source_pts_seconds: number;
  notes?: readonly {lane: number; x: number; y: number}[];
}
export interface PreparedObservations {
  frames: readonly CounterFrame[];
  visibility_frames: readonly VisibilityFrame[];
  occluders: readonly Evidence[];
  native_body_risk_available: boolean;
  pre_hold_proofs: Readonly<Record<string, Evidence>>;
  configured_processing?: {input: Evidence; output: Evidence};
  source_artifacts?: Readonly<Record<string, readonly [number, number | bigint] | null>>;
}
export interface PresentationInput {
  schema: 2;
  source: InspectionSource;
  observations: Immutable<PreparedObservations>;
  artifact_root?: string;
}

/** The native measurement is inserted only when the prepared input supplies it. */
export const interpretationOrder = ['hold-view', 'motion-effects'] as const;
export const inspectionOrder = [
  ...interpretationOrder, 'configured-processing', 'effect-view', 'policy-view', 'timing-ranges', 'visibility', 'diagnostics',
] as const;
export type ViewStage = typeof inspectionOrder[number];
export type ViewArtifact = Artifact<ViewStage, Evidence>;
export interface InspectionResult {stages: readonly ViewArtifact[]}
export type InspectionArtifact = BoundArtifact<'inspection', InspectionResult>;
export type InterpretationArtifact = BoundArtifact<'interpretation', InspectionResult>;

export function input(data: RecordData, observations: PreparedObservations, artifactRoot?: string): PresentationInput {
  return {
    schema: 2, source: capture(data), observations,
    ...(artifactRoot ? {artifact_root: artifactRoot.replace(/\/+$/, '') + '/'} : {}),
  };
}
