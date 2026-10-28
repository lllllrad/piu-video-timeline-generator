import {createHash} from 'node:crypto';
import {text, type Document} from './ucs.ts';
import type {RecordData} from '../types.ts';

export function transcriptionAlignment(template: Document, data: RecordData, alignment: RecordData): [RecordData, RecordData] {
  const result = {...alignment}, proof = {method: 'audio_alignment', song_start_seconds: alignment.song_start_seconds, uncertainty_seconds: alignment.uncertainty_seconds};
  const beat = data.beat_timing ?? {}, phase = beat.song_phase_correction_seconds;
  if (phase == null) return [result, proof];
  const ref = beat.contract?.reference ?? {}, expected = createHash('sha256').update(text(template)).digest('hex');
  if (ref.status !== 'available' || ref.sha256 !== expected || ref.song_start_seconds !== alignment.song_start_seconds ||
    ref.alignment_uncertainty_seconds !== alignment.uncertainty_seconds || (alignment.rate ?? 1) !== 1) {
    return [result, {...proof, unused_phase_reason: 'phase_reference_does_not_match_transcription_alignment'}];
  }
  const bounds = beat.song_phase_range, finite = v => typeof v === 'number' && Number.isFinite(v);
  if (!finite(phase) || !Array.isArray(bounds) || bounds.length !== 2 || !bounds.every(finite) ||
    !(-alignment.uncertainty_seconds <= bounds[0] && bounds[0] <= phase && phase <= bounds[1] && bounds[1] <= alignment.uncertainty_seconds) ||
    !(beat.groups ?? []).some(g => g.status === 'restored')) throw new Error('Invalid bounded common song phase for UCS transcription');
  const origin = alignment.song_start_seconds + phase, uncertainty = Math.max(phase - bounds[0], bounds[1] - phase);
  Object.assign(result, {song_start_seconds: origin, uncertainty_seconds: uncertainty});
  return [result, {method: 'bounded_common_song_phase', audio_song_start_seconds: alignment.song_start_seconds, audio_uncertainty_seconds: alignment.uncertainty_seconds,
    phase_correction_seconds: phase, phase_range: [...bounds], song_start_seconds: origin, uncertainty_seconds: uncertainty, timing_sha256: expected}];
}
