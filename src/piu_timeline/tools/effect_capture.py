"""Acquire source-bound RGB windows for the TypeScript effect-reference tool."""
import argparse
import bisect
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from piu_timeline import ROOT
from piu_timeline.play.frames import decode_frames


def candidates(trace, limit=None):
    groups = [[] for _ in range(5)]
    recent = {}
    for i, row in enumerate(trace):
        for lane, value in enumerate(row['receptor_white_fraction']):
            before = trace[max(0, i-6):i]
            onset = len(before) == 6 and all(r['receptor_lit'][lane] is False for r in before)
            rise = i > 0 and value-trace[i-1]['receptor_white_fraction'][lane] > .18
            boundary = i == 0
            if value <= .55 or not (onset or rise or boundary):
                continue
            if limit is not None and (not onset or i < 8 or i >= len(trace)-26):
                continue
            if not onset and row['playback_seconds']-recent.get(lane, -100) < .10:
                continue
            kind = 'off_to_on_candidate' if onset else 'boundary_bright_candidate' if boundary else 'rebrightening_candidate'
            groups[lane % 5].append((i, lane, kind)); recent[lane] = row['playback_seconds']
    chosen = []
    for group in groups:
        indices = range(len(group)) if limit is None else np.linspace(0, len(group)-1, min(limit, len(group)), dtype=int)
        chosen.extend(group[i] for i in indices)
    return sorted(chosen)


def capture(directory, output, limit, *, data=None):
    data = data if data is not None else json.loads((directory/'analysis.json').read_text())
    trace = [json.loads(line) for line in (directory/'hold-frames.jsonl').open()]
    chosen = candidates(trace, limit)
    if not chosen and limit is not None:
        raise ValueError('No off-to-on candidate windows; no references invented')
    times = [r['playback_seconds'] for r in trace]
    events = []
    desired = {}
    for n, (i, lane, selection_kind) in enumerate(chosen):
        event = {'id': f'{directory.parent.parent.name}-{directory.name}-{i}-lane{lane}',
                 'lane': lane, 'kind': lane % 5, 'marker': times[i], 'selection_kind': selection_kind, 'frames': []}
        events.append(event)
        for index in range(max(0, i-8), min(len(trace), i+26)):
            desired.setdefault(index, []).append(n)
    notes = {}
    with (directory/'frames.jsonl').open() as stream:
        for i, line in enumerate(stream):
            if i in desired:
                row = json.loads(line)
                if abs(row['source_pts_seconds']-trace[i]['source_pts_seconds']) > 1e-6:
                    raise ValueError('Note timeline differs from receptor timeline')
                notes[i] = row.get('notes', [])
    if set(notes) != set(desired):
        raise ValueError('Missing source-bound note frames for exclusion acquisition')
    source = Path(data['media']['path'])
    before = source.stat()
    output.mkdir(parents=True, exist_ok=False)
    spacing = float(np.median(np.diff([l['x']*650 for l in data['layout']['lanes']])))
    rgb_path, mask_path = output/'pixels.rgb', output/'exclusions.bin'
    offset = 0
    written = {}
    with rgb_path.open('wb') as pixels, mask_path.open('wb') as masks:
        for pts, t, rgb in (decode_frames(data['media'], times[min(desired)],
                                         times[max(desired)]+.001, data['game_roi'], 650) if desired else []):
            i = bisect.bisect_left(times, t-1e-6)
            if i >= len(times) or abs(times[i]-t) > 1e-6 or abs(trace[i]['source_pts_seconds']-pts) > 1e-6:
                raise ValueError('Decoded PTS differs from retained source timeline')
            height = rgb.shape[0]
            y = round(data['layout']['receptor_y']*height)
            for event_index in desired.get(i, []):
                event = events[event_index]
                if (i, event['lane']) in written:
                    event['frames'].append(written[i, event['lane']]); continue
                x = round(data['layout']['lanes'][event['lane']]['x']*650)
                patch = rgb[y-23:y+24, x-23:x+24]
                if patch.shape != (47, 47, 3):
                    raise ValueError('Receptor crop clipped by game ROI')
                boxes = []
                for note in notes.get(i, []):
                    nx, ny, radius = note['x']*650, note['y']*height, spacing/2
                    boxes.append([nx-radius, ny-radius, nx+radius, ny+radius])
                scale_y = height/round(325*data['game_roi'][3]/data['game_roi'][2])
                for body in trace[i].get('bodies', []):
                    box = body.get('foreground_bounds')
                    if box:
                        boxes.append([box[0]*2, box[1]*scale_y, box[2]*2, box[3]*scale_y])
                mask = np.zeros((47, 47), dtype='uint8')
                used = []
                for left, top, right, bottom in boxes:
                    l, r = max(0, int(np.floor(left-x+23))), min(47, int(np.ceil(right-x+23)))
                    a, b = max(0, int(np.floor(top-y+23))), min(47, int(np.ceil(bottom-y+23)))
                    if l < r and a < b:
                        mask[a:b, l:r] = 1
                        used.append([left, top, right, bottom])
                pixels.write(patch.tobytes()); masks.write(mask.tobytes())
                event['frames'].append({'offset': offset, 'pts': pts, 'time': t,
                                        'crop': [x-23, y-23, 47, 47], 'envelopes': used})
                written[i, event['lane']] = event['frames'][-1]
                offset += 1
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Original source changed during capture')
    manifest = {'schema': 1, 'producer_sha256': sha256(Path(__file__).read_bytes()).hexdigest(), 'source': str(source), 'segment': str(directory),
                'selection': 'all_light_candidates' if limit is None else 'sampled_off_to_on',
                'game_roi': data['game_roi'], 'layout': data['layout'], 'segment_number': data.get('segment_number'),
                'source_identity': {'size': before.st_size, 'mtime_ns': before.st_mtime_ns},
                'pixels_sha256': sha256(rgb_path.read_bytes()).hexdigest(),
                'exclusions_sha256': sha256(mask_path.read_bytes()).hexdigest(),
                'pixel_policy': '47x47 RGB at game width 650; original PTS; no retiming',
                'exclusion_policy': 'Conservative observed note-center and body-bounds envelopes; not verified opacity or layer order',
                'events': events}
    (output/'capture.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Captured {len(events)} windows, {offset} original-PTS patches: {output}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--play', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--per-direction', type=int, default=12)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()):
        parser.error('Output must be under .local; use a new directory')
    if not 3 <= args.per_direction <= 100:
        parser.error('--per-direction must be between 3 and 100')
    capture(args.play.resolve(), output, args.per_direction)


if __name__ == '__main__':
    main()
