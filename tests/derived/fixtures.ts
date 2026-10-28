/** Independent chart events sampled into the saved native-observation contract. */
import type {RecordData} from '../../src/piu_timeline/derived/types.ts';
import {parse} from '../../src/piu_timeline/derived/charts/ucs.ts';

export function template(split = 48, rows = 384) {
  return parse(`:Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=${split}\n` + '.....\n'.repeat(rows));
}

export interface NativeCapture {
  end?: number;
  repeated?: [number, number][];
  dropped?: number[];
}
export function nativeScene(events: [number, number][], spacing = 40, fps = 60, lanes = 5, capture: NativeCapture = {}): RecordData {
  const width = spacing * 16.25, height = spacing * 9.125, receptor = spacing * 1.3, velocity = spacing * 6;
  const times = Array.from({length: Math.round(((capture.end ?? 1.05) - .2) * fps) + 1}, (_, i) => .2 + i / fps).filter((_, i) => !capture.dropped?.includes(i));
  const rendered = (time: number) => {
    const interval = capture.repeated?.find(([lo, hi]) => lo - 1e-9 <= time && time <= hi + 1e-9);
    if (!interval) return time;
    const before = times.filter(t => t < interval[0] - 1e-9).at(-1);
    if (before === undefined) throw Error('Repeated frame requires an earlier captured image');
    return before;
  };
  const notes = [], registrations = [], offsets = [];
  events.forEach(([target, lane], index) => {
    const points = times.map(t => [t, receptor + velocity * (target - rendered(t))])
      .filter(([, y]) => receptor + .85 * spacing < y && y < .95 * height - .55 * spacing);
    notes.push({lane, status: 'estimated', target_seconds: target, prediction_uncertainty_seconds: .5 / fps, points,
      motion_clock: {origin: 0, velocity, intercept: 0}, motion_target_phase: velocity * target});
    registrations.push({note: index, status: 'registered', coordinate_method: 'native_cap_measurements', coordinate_uncertainty_pixels: .025 * spacing,
      observations: points.map(([time]) => ({time, source_pts_seconds: 80 + time}))});
    offsets.push({note: index, offset_pixels: receptor + velocity * target});
  });
  return {analysis_width: width, analysis_height: height, start_seconds: .2, end_seconds: 2.2,
    layout: {receptor_y: receptor / height, note_y_max: .95, lanes: Array.from({length: lanes}, (_, i) => ({x: .1 + i * spacing / width}))},
    notes, head_registration: {notes: registrations},
    scroll_motion: {samples: times.map(time => ({time, source_pts: 80 + time, phase: velocity * rendered(time), variance: 0, support: lanes, chunk: 0})),
      coordinate_registration: {chunks: [{chunk: 0, status: 'fitted', head_offsets: offsets}]}}};
}

/** Captured endpoints with independent registration errors; truth stays rigid. */
export function holdEndpointScene(length: number, scale = 1, delays: number[] = []) {
  const times = Array.from({length: 12}, (_, i) => .2 + i / 60 + (delays[i] ?? 0));
  const headError = [-.75, .5, -.25, .75], tailError = [.75, -.5, .25, -.75];
  return times.map((time, i) => ({time, source_pts_seconds: 80 + time,
    head_y: scale * (200 - 180 * time + headError[i % 4]),
    tail_y: scale * (200 - 180 * time + length + tailError[i % 4]), head_uncertainty: scale, tail_uncertainty: scale}));
}
