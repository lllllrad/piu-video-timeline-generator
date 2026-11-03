/** Affine parameters define a clock; crossing diagnostics belong to each note. */
import {equal}from '../math.ts';
import type {RecordData}from '../types.ts';
export interface ClockParameters extends RecordData {origin:number;velocity:number;intercept:number;residual:number;window:[number,number]}
export const crossingFields=['selection','trimmed_outer_frames','bracket_phase_errors_pixels','bracket_tolerance_pixels']as const;
export function parameters(clock:RecordData):RecordData{
 return Object.fromEntries(Object.entries(clock).filter(([k])=>!(crossingFields as readonly string[]).includes(k)).sort(([a],[b])=>a.localeCompare(b)));
}
export function same(first:RecordData|null,second:RecordData|null):boolean{
 return !!first&&!!second&&equal(parameters(first),parameters(second));
}
