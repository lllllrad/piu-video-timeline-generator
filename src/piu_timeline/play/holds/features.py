"""Native-frame hold pixels and their source/geometry cache contract."""
from itertools import zip_longest
import json
from pathlib import Path

import cv2
import numpy as np

from piu_timeline.play.frames import decode_frames

FEATURE_FORMAT = {'schema': 1, 'detector_revision': 6, 'width': 325}


def ui_regions(layout):
    """Regions where the HUD can interrupt an independently visible stripe."""
    if 'combo_roi' not in layout:
        return []
    from piu_timeline.play.judgments import judgment_region
    x, y, w, h = layout['combo_roi']
    return [judgment_region(layout), [x, y-.06, w, h+.06]]


def bridge_ui_stripes(mask, top, left, layout, width, height, spacing):
    """Join two extended stripes across a HUD gap, never adjacent tap caps."""
    original = mask.copy()
    _, labels, stats, _ = cv2.connectedComponentsWithStats(original, 8)
    parts = [(i, s) for i, s in enumerate(stats[1:], 1) if s[3] > 1.6*spacing and s[2] > .16*spacing]
    regions = ui_regions(layout)
    for i, first in enumerate(parts):
        for second in parts[i+1:]:
            (ai, a), (bi, b) = sorted((first, second), key=lambda part: part[1][1])
            gap = b[1]-(a[1]+a[3])
            if not 0 < gap <= .9*spacing:
                continue
            for col in range(max(a[0], b[0]), min(a[0]+a[2], b[0]+b[2])):
                upper = np.flatnonzero(labels[:, col] == ai)
                lower = np.flatnonzero(labels[:, col] == bi)
                # Ragged colored edges need not end on the bounding box's
                # final row in the same column. Follow actual stripe pixels.
                if len(upper) < .8*spacing or len(lower) < .8*spacing:
                    continue
                end, start = int(upper[-1]), int(lower[0])
                if (0 < start-end <= 1.6*spacing
                        and any(x*width <= col+left <= (x+w)*width
                                and y*height <= end+top and start+top <= (y+h)*height
                                for x, y, w, h in regions)):
                    mask[end:start+1, col] = 1
    return mask


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
        original_mask = mask.copy()
        mask = bridge_ui_stripes(mask, top, left, layout, width, height, spacing)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for component, (x, y, w, h, area) in enumerate(stats[1:count], 1):
            if h < .8 * spacing or w < .16 * spacing or area < .35 * w * h:
                continue
            stripe = (labels[y:y+h, x:x+w] == component).mean(axis=0).max()
            if stripe < .72:
                continue
            def in_hud(edge):
                return any(rx*width <= cx <= (rx+rw)*width and ry*height <= edge <= (ry+rh)*height
                           for rx, ry, rw, rh in ui_regions(layout))
            bodies.append({'lane': index, 'top': float(y + top), 'bottom': float(y + top + h),
                           'edge_convention': 'connected_color',
                           'top_visible': bool(not in_hud(y+top) and y+top > receptor+.3*spacing),
                           'long': bool(h > 1.6 * spacing),
                           'stripe_support': float(original_mask[y:y+h, x:x+w].mean(axis=0).max()),
                           'tail_visible': bool(y+top+h < bottom-.65*spacing and not in_hud(y+top+h))})
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
                from piu_timeline.play.receptors import fractions
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
