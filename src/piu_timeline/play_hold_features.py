"""Native-frame hold pixels and their source/geometry cache contract."""
from itertools import zip_longest
import json
from pathlib import Path

import cv2
import numpy as np

from .play_frames import decode_frames

FEATURE_FORMAT = {'schema': 1, 'detector_revision': 4, 'width': 325}


def feature_contract(data):
    return {'format': FEATURE_FORMAT, **{key: data[key] for key in
            ('media', 'start_seconds', 'end_seconds', 'game_roi', 'layout')}}


def detect_bodies(rgb, layout):
    """Observe colored vertical bodies and filled receptors without reading text."""
    height, width = rgb.shape[:2]
    spacing = float(np.median(np.diff([lane['x'] * width for lane in layout['lanes']])))
    receptor = layout['receptor_y'] * height
    hue, saturation, value = cv2.split(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV))
    colors = {'blue': (hue >= 85) & (hue <= 130), 'red': (hue <= 28) | (hue >= 150),
              'yellow': (hue >= 15) & (hue <= 45)}
    white = (rgb.min(axis=2) > 190) & (rgb.max(axis=2) - rgb.min(axis=2) < 65)
    bodies, lit = [], []
    top, bottom = max(0, int(receptor - .3 * spacing)), min(height, int(layout.get('note_y_max', .95) * height))
    for index, lane in enumerate(layout['lanes']):
        cx = lane['x'] * width
        left, right = max(0, int(cx - .38 * spacing)), min(width, int(cx + .38 * spacing))
        ry1, ry2 = max(0, int(receptor - .28 * spacing)), min(height, int(receptor + .28 * spacing))
        rx1, rx2 = max(0, int(cx - .28 * spacing)), min(width, int(cx + .28 * spacing))
        lit.append(float(white[ry1:ry2, rx1:rx2].mean()) > .55)
        mask = (colors[lane['color']] & (saturation > 105) & (value > 170))[top:bottom, left:right].astype('uint8')
        # Small holes from judgment text can split an otherwise continuous body.
        original_mask = mask.copy()
        kernel = np.ones((max(3, round(.6 * spacing)) | 1, 1), dtype='uint8')
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for component, (x, y, w, h, area) in enumerate(stats[1:count], 1):
            if h < .8 * spacing or w < .16 * spacing or area < .35 * w * h:
                continue
            stripe = (labels[y:y+h, x:x+w] == component).mean(axis=0).max()
            if stripe < .72:
                continue
            bodies.append({'lane': index, 'top': float(y + top), 'bottom': float(y + top + h),
                           'long': bool(h > 1.6 * spacing),
                           'stripe_support': float(original_mask[y:y+h, x:x+w].mean(axis=0).max()), 'tail_visible': bool(y + top + h < bottom - .65 * spacing)})
    return bodies, lit


def acquire_features(data, output):
    contract = feature_contract(data)
    header, trace = output / 'hold-features.json', output / 'hold-frames.jsonl'
    if header.is_file() and trace.is_file() and json.loads(header.read_text()).get('contract') == contract:
        return
    print('  Extracting long-note bodies and receptor states; no OCR...', flush=True)
    temporary = trace.with_suffix('.build-jsonl')
    width = FEATURE_FORMAT['width']
    original = output / 'frames.jsonl'
    count = 0
    source_before = Path(data['media']['path']).stat()
    try:
        with original.open() as saved, temporary.open('w') as target:
            frames = decode_frames(data['media'], data['start_seconds'], data['end_seconds'], data['game_roi'], width)
            for raw, decoded in zip_longest(saved, frames):
                if raw is None or decoded is None:
                    raise ValueError('Hold acquisition frame count differs from saved native frames')
                previous = json.loads(raw)
                pts, time, image = decoded
                if abs(pts - previous['source_pts_seconds']) > 1e-6 or abs(time - previous['playback_seconds']) > 1e-6:
                    raise ValueError('Hold acquisition PTS differs from saved native frames')
                bodies, lit = detect_bodies(image, data['layout'])
                from .play_receptors import fractions
                scores = fractions(image, data['layout'])
                target.write(json.dumps({'source_pts_seconds': pts, 'playback_seconds': time,
                                         'bodies': bodies, 'receptor_lit': lit, 'receptor_white_fraction': scores}) + '\n')
                count += 1
                if count % 2400 == 0:
                    print(f'    Long notes: {time-data["start_seconds"]:.0f}/{data["end_seconds"]-data["start_seconds"]:.0f}s', flush=True)
        source_after = Path(data['media']['path']).stat()
        if (source_before.st_size, source_before.st_mtime_ns) != (source_after.st_size, source_after.st_mtime_ns):
            raise ValueError('Source changed during long-note acquisition')
        temporary.replace(trace)
        pending = header.with_suffix('.build-json')
        pending.write_text(json.dumps({'contract': contract, 'frame_count': count}) + '\n')
        pending.replace(header)
    finally:
        temporary.unlink(missing_ok=True)
