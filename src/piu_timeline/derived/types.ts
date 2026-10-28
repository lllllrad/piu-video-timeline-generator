/** Retained data has extensible provenance; algorithms type the fields they own. */
export type RecordData = Record<string, any>;
export type Interval = [number, number];
export interface Head extends RecordData {offset: number; lane: number}
export interface Reference extends Head {note: number; target_seconds: number}
export interface CoordinateModel {
  coordinate_domain: {vertices: [number, number][]; maximum_reference_error_pixels: number};
  lane_spacing_pixels: number;
  velocity_pixels_per_second: number;
  origin_seconds: number;
  offset_at_origin_pixels: number;
  maximum_reference_error_pixels: number;
  reference_target_range: Interval;
  references: Reference[];
}
export interface Note extends RecordData {
  lane: number;
  status: string;
  points: Interval[];
  target_seconds: number | null;
  prediction_uncertainty_seconds: number;
}
export interface CoordinateSupport {
  lane_spacing_pixels: number;
  chunks: Record<string, Record<string, Head>>;
  frames: Record<string, number>;
  observed: Record<string, number[]>;
  reference_notes: number[];
  recovery_reference_sets?: RecordData[];
}
