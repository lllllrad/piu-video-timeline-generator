"""Native-frame hold pixels and their source/geometry cache contract."""
from itertools import zip_longest
import json
from pathlib import Path

import cv2
import numpy as np

from piu_timeline.play.frames import decode_frames

FEATURE_FORMAT = {'schema': 1, 'detector_revision': 10, 'width': 325,
                  'continuity': 'three_row_strong_and_relaxed_color_columns',
                  'processing_pixels': 'lane_color_white_and_visibility_masks_v1'}


def ui_regions(layout):
    """Regions where the HUD can interrupt an independently visible stripe."""
    from piu_timeline.play.screen_regions import note_occluders
    return [region['rect'] for region in note_occluders(layout)]


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


def connector_rows(mask, top, spacing, relaxed=None):
    """Rows with a colored vertical connector, before any white/HUD repair."""
    widths = (mask[:-2] & mask[1:-1] & mask[2:]).sum(axis=1)
    relaxed = mask if relaxed is None else relaxed
    possible = (relaxed[:-2] & relaxed[1:-1] & relaxed[2:]).sum(axis=1)
    def ranges(values):
        edges = np.flatnonzero(np.diff(np.r_[False, False, values, False, False]))
        return [[int(a+top), int(b+top)] for a,b in zip(edges[::2], edges[1::2])]
    return {'connected': ranges(widths >= max(2, .12*spacing)),
            'disconnected': ranges(possible == 0)}


def detect_bodies(rgb, layout, connections=None):
    """Observe colored vertical bodies and filled receptors without reading text."""
    from piu_timeline.play.pixel_cache import measurements
    return detect_body_masks(measurements(rgb), layout, connections)


def detect_body_masks(planes, layout, connections=None):
    """Interpret retained color masks without reacquiring source pixels."""
    height, width = planes['white'].shape
    spacing = float(np.median(np.diff([lane['x'] * width for lane in layout['lanes']])))
    receptor = layout['receptor_y'] * height
    white = planes['white']
    bodies, lit = [], []
    top, bottom = max(0, int(receptor - .3 * spacing)), min(height, int(layout.get('note_y_max', .95) * height))
    for index, lane in enumerate(layout['lanes']):
        cx = lane['x'] * width
        left, right = max(0, int(cx - .38 * spacing)), min(width, int(cx + .38 * spacing))
        ry1, ry2 = max(0, int(receptor - .28 * spacing)), min(height, int(receptor + .28 * spacing))
        rx1, rx2 = max(0, int(cx - .28 * spacing)), min(width, int(cx + .28 * spacing))
        lit.append(float(white[ry1:ry2, rx1:rx2].mean()) > .55)
        mask = planes['body_'+lane['color']][top:bottom, left:right].astype('uint8')
        original_mask = mask.copy()
        _,source_labels=cv2.connectedComponents(original_mask,connectivity=8)
        if connections is not None:
            relaxed = planes['relaxed_'+lane['color']][top:bottom, left:right]
            connections.append(connector_rows(original_mask, top, spacing, relaxed))
        mask = bridge_ui_stripes(mask, top, left, layout, width, height, spacing)
        # A cap's thin white border can disconnect its colored interior
        # from a genuine short body. Restore only observed nearby white pixels;
        # never fill background between two arrows.
        border = max(3, round(.16*spacing)) | 1
        near_color = cv2.dilate(original_mask, np.ones((border, border), dtype='uint8')) > 0
        white_mask = original_mask | (white[top:bottom, left:right] & near_color).astype('uint8')
        for candidate_mask, white_bridge in ((mask, False), (white_mask, True)):
            count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate_mask, 8)
            for component, (x, y, w, h, area) in enumerate(stats[1:count], 1):
                if h < .8 * spacing or w < .16 * spacing or area < .35 * w * h:
                    continue
                if white_bridge:
                    if not 1.6*spacing < h <= 3.5*spacing:
                        continue
                    middle = y+h//2
                    connection = original_mask[middle-1:middle+2, x:x+w]
                    # A real short body carries a colored connector between its
                    # caps. White borders touching across a tap gap are insufficient.
                    if np.all(connection, axis=0).sum() < max(2, .12*spacing):
                        continue
                    if any(b['lane'] == index and abs(b['top']-(y+top)) <= 2
                           and abs(b['bottom']-(y+top+h)) <= 2 for b in bodies):
                        continue
                stripe = (labels[y:y+h, x:x+w] == component).mean(axis=0).max()
                if stripe < .72:
                    continue
                def in_hud(edge):
                    return any(rx*width <= cx <= (rx+rw)*width and ry*height <= edge <= (ry+rh)*height
                               for rx, ry, rw, rh in ui_regions(layout))
                source_ids=np.unique(source_labels[y:y+h,x:x+w][labels[y:y+h,x:x+w]==component])
                bodies.append({'lane': index, 'top': float(y + top), 'bottom': float(y + top + h),
                               'source_components':[int(i)for i in source_ids if i],
                               'foreground_bounds':[int(left+x),int(top+y),int(left+x+w),int(top+y+h)],
                               'edge_convention': 'connected_color', 'white_cap_bridge': white_bridge,
                               'top_visible': bool(not in_hud(y+top) and y+top > receptor+.3*spacing),
                               'long': bool(h > 1.6 * spacing),
                               'stripe_support': float(original_mask[y:y+h, x:x+w].mean(axis=0).max()),
                               'tail_visible': bool(y+top+h < bottom-.65*spacing and not in_hud(y+top+h))})
    return bodies, lit


def acquire_features(data, output):
    contract = feature_contract(data)
    header, trace = output / 'hold-features.json', output / 'hold-frames.jsonl'
    if header.is_file() and trace.is_file() and json.loads(header.read_text()).get('contract') == contract and (output/'processing-features.npz').is_file():
        return
    print('  Extracting long-note bodies and receptor states; no OCR...', flush=True)
    temporary = trace.with_suffix('.build-jsonl')
    width = FEATURE_FORMAT['width']
    original = output / 'frames.jsonl'
    count, pixels = 0, None
    source_before = Path(data['media']['path']).stat()
    try:
        with original.open() as saved, temporary.open('w') as target:
            from piu_timeline.play.pixel_cache import native_measurements
            frames = native_measurements(data, output, decode_frames)
            for raw, decoded in zip_longest(saved, frames):
                if raw is None or decoded is None:
                    raise ValueError('Hold acquisition frame count differs from saved native frames')
                previous = json.loads(raw)
                pts, time, planes, scores = decoded
                if abs(pts - previous['source_pts_seconds']) > 1e-6 or abs(time - previous['playback_seconds']) > 1e-6:
                    raise ValueError('Hold acquisition PTS differs from saved native frames')
                if pixels is None:
                    from piu_timeline.play.processing import ReceptorPixels
                    pixels = ReceptorPixels(data['layout'], width, planes['white'].shape[0])
                pixels.observe_masks(planes, pts, time)
                connections = []
                bodies, lit = detect_body_masks(planes, data['layout'], connections)
                target.write(json.dumps({'source_pts_seconds': pts, 'playback_seconds': time,
                                         'bodies': bodies, 'receptor_lit': lit, 'receptor_white_fraction': scores,
                                         'color_connections': connections}) + '\n')
                count += 1
                if count % 2400 == 0:
                    print(f'    Long notes: {time-data["start_seconds"]:.0f}/{data["end_seconds"]-data["start_seconds"]:.0f}s', flush=True)
        source_after = Path(data['media']['path']).stat()
        if (source_before.st_size, source_before.st_mtime_ns) != (source_after.st_size, source_after.st_mtime_ns):
            raise ValueError('Source changed during long-note acquisition')
        if pixels is not None:
            from piu_timeline.play.pixel_cache import source_contract
            pixels.save(output/'processing-features.npz', source_contract(data))
        temporary.replace(trace)
        pending = header.with_suffix('.build-json')
        pending.write_text(json.dumps({'contract': contract, 'frame_count': count}) + '\n')
        pending.replace(header)
    finally:
        temporary.unlink(missing_ok=True)
