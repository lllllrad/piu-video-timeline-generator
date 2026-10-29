/** Explicit consumer inputs; native acquisition metadata never becomes numerical state. */
import type {RecordData} from '../types.ts';
import {measurementInput} from '../native_gaps.ts';
import {implementation} from './store.ts';
export const coordinateProducer = (): string => implementation(new URL('../coordinates/measurements.ts', import.meta.url));
export const processingProducer = (): string => implementation(new URL('../scroll.ts', import.meta.url));
export const pick = (data: RecordData, keys: readonly string[]): RecordData => Object.fromEntries(keys.filter(k => Object.hasOwn(data, k)).map(k => [k, data[k]]));
export const viewFields = ['notes', 'matches', 'limitations', 'excluded_notes', 'miss_candidates', 'combo_events', 'judgment_events',
  'hold_tick_ambiguous_notes', 'recovered_pre_hold_notes', 'recovered_dense_notes', 'recovered_lane_supported_notes','recovered_bounded_target_notes', 'hold_analysis',
  'coverage', 'note_type_diagnostics', 'conflicted_matches', 'association_view_format'];
export function processingChannel(data: RecordData): RecordData {
  const channel = data.visual_channels?.processing ?? {};
  return {...pick(channel, ['visibility_boundaries','format','pixel_coordinates']), notes: (channel.notes ?? []).map(n => ({
    ...pick(n, ['note', 'id', 'lane', 'status', 'reason', 'range', 'source_pts_seconds', 'confirmation_source_pts_seconds',
      'passage_evidence', 'cap_coverage', 'cap_observation', 'visibility_loss', 'gimmick_candidates', 'native_status', 'native_reason', 'motion_basis']), sample_count: n.samples?.length ?? n.sample_count ?? 0}))};
}
export function evidence(data: RecordData): RecordData {
  const result = pick(data, ['notes', 'matches', 'conflicted_matches', 'miss_candidates', 'combo_events', 'judgment_events', 'counter_frame_events',
    'display_delay_correction_ms', 'median_frame_interval_seconds', 'chart_policy', 'unsupported_intervals', 'coverage']);
  result.hold_analysis = pick(data.hold_analysis ?? {}, ['holds', 'receptor_runs', 'unresolved_tracks']);
  const channels = data.visual_channels ?? {};
  result.visual_channels = Object.fromEntries(['receptors', 'processing'].filter(k => channels[k]).map(k => [k, pick(channels[k], [k === 'receptors' ? 'events' : 'notes'])]));
  if (channels.processing) result.visual_channels.processing = processingChannel(data);
  return result;
}
export function interpretation(data: RecordData, riskAvailable: boolean): RecordData {
  const result: RecordData = {...evidence(data), ...pick(data, ['notes', 'hold_analysis', 'skin_detector', 'limitations', 'counter_judgment_labels', 'deferred_matches']),
    native_body_risk_available: riskAvailable};
  Object.assign(result,pick(data,['analysis_width','analysis_height']));
  result.head_registration=measurementInput(data.head_registration??{});
  if(data.layout)result.layout={...pick(data.layout,['receptor_y','note_y_max']),lanes:(data.layout.lanes??[]).map(l=>pick(l,['x']))};
  result.scroll_motion={samples:(data.scroll_motion?.samples??[]).map(s=>pick(s,['time','source_pts','chunk'])),
    coordinate_registration:{chunks:(data.scroll_motion?.coordinate_registration?.chunks??[]).map(c=>({
      ...pick(c,['chunk','status']),head_offsets:(c.head_offsets??[]).map(h=>pick(h,['note']))}))}};
  result.visual_channels = {...result.visual_channels, ...pick(data.visual_channels ?? {}, ['note_types', 'timeline'])};
  return result;
}
export function processing(data: RecordData): RecordData {
  return {...pick(data, ['media', 'start_seconds', 'end_seconds', 'layout', 'game_roi', 'analysis_width', 'analysis_height', 'notes',
    'scroll_motion', 'scroll_pause_model', 'scroll_speed_model', 'skin_detector', 'skin_role_evidence', 'object_interpretation']),
    hold_analysis: {holds: (data.hold_analysis?.holds ?? []).map(h => Object.fromEntries(Object.entries(h).filter(([k]) => k !== 'input')))}};
}
export function visibility(data: RecordData): RecordData {
  return {...pick(data, ['layout', 'analysis_width', 'analysis_height', 'scroll_pause_model', 'scroll_speed_model']),
    notes: (data.notes ?? []).map(n => pick(n, ['lane', 'points', 'detected_points', 'head_registration'])),
    scroll_motion: {samples: (data.scroll_motion?.samples ?? []).map(s => pick(s, ['time', 'phase', 'chunk', 'coordinate_status', 'support']))},
    visual_channels: {processing: processingChannel(data)}};
}
export function recognition(data: RecordData): RecordData {
  return {...pick(data, ['notes', 'matches', 'conflicted_matches', 'chart_policy', 'visual_support', 'skin_detector', 'start_seconds', 'end_seconds',
    'object_interpretation', 'timing_reconstruction', 'beat_timing', 'head_registration', 'skin_role_evidence', 'body_risk_evidence',
    'visibility_diagnostics', 'note_type_diagnostics', 'hold_analysis']), visual_channels: {processing: processingChannel(data)}};
}
