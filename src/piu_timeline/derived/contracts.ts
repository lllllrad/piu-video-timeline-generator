import {readFileSync} from 'node:fs';
export const contracts = JSON.parse(readFileSync(new URL('./contracts.json', import.meta.url), 'utf8'));
contracts.image_coordinates.native_cap_registration = contracts.native_anchor;
Object.assign(contracts.chords, {native_cap_registration: contracts.native_anchor, image_coordinates: contracts.image_coordinates});
for (const key of ['domains', 'recovery']) contracts[key].measurement_limits = contracts.coordinates;
Object.assign(contracts.timing, {clock_conversion: contracts.clock_conversion, spacing_checks: contracts.spacing,
  independent_coordinates: contracts.coordinates, native_chords: contracts.chords, native_row_domains: contracts.domains, native_recovery: contracts.recovery,
  native_gap_validation: contracts.native_gap_validation});
export const NATURAL_SPLITS: number[] = contracts.natural_splits;
for (const key of ['timing', 'recovery', 'transcription']) contracts[key].natural_splits = NATURAL_SPLITS;
export const RECOVERABLE = ['shared_timing_reconstruction_failed', 'shared_spacing_reconstruction_conflict'];
