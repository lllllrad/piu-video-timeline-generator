/** Independent chart events sampled into the saved native-observation contract. */
import type {RecordData} from '../../src/piu_timeline/derived/types.ts';
import {parse} from '../../src/piu_timeline/derived/charts/ucs.ts';

export function template(split = 48, rows = 384) {
  return parse(`:Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=${split}\n` + '.....\n'.repeat(rows));
}

export function nativeScene(events: [number, number][], spacing = 40, fps = 60, lanes = 5): RecordData {
  const width = spacing * 16.25, height = spacing * 9.125, receptor = spacing * 1.3, velocity = spacing * 6;
  const times = Array.from({length: Math.round(.85 * fps) + 1}, (_, i) => .2 + i / fps);
  const notes = [], registrations = [], offsets = [];
  events.forEach(([target, lane], index) => {
    const points = times.map(t => [t, receptor + velocity * (target - t)])
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
    scroll_motion: {samples: times.map(time => ({time, source_pts: 80 + time, phase: velocity * time, chunk: 0})),
      coordinate_registration: {chunks: [{chunk: 0, status: 'fitted', head_offsets: offsets}]}}};
}
