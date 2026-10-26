"""Bounded native feature storage, independent of body and event detectors."""
import json
from pathlib import Path
import shutil
from itertools import zip_longest

import cv2
import numpy as np

FORMAT = {'schema': 1, 'width': 325, 'measurement': 'color_threshold_planes_v1', 'chunk_frames': 128}
COLORS = ('blue', 'red', 'yellow')
FIELDS = [prefix+color for prefix in ('body_', 'relaxed_', 'processing_') for color in COLORS]+['white', 'visible']


def source_contract(data):
    return {key: data[key] for key in ('media', 'start_seconds', 'end_seconds', 'game_roi', 'layout')}


def processing_contract_matches(saved, data):
    """Normalize the old detector-coupled envelope only at the cache boundary."""
    from piu_timeline.play.processing import PIXEL_FORMAT
    source = saved.get('source', {})
    return (saved.get('format') == PIXEL_FORMAT
            and {key: value for key, value in source.items() if key != 'format'} == source_contract(data))


def measurements(rgb):
    hue, saturation, value = cv2.split(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV))
    colors = {'blue': (hue >= 85) & (hue <= 130), 'red': (hue <= 28) | (hue >= 150),
              'yellow': (hue >= 15) & (hue <= 45)}
    result = {}
    for prefix, sat, light in (('body_', 105, 170), ('relaxed_', 60, 90), ('processing_', 90, 140)):
        for color in COLORS:
            mask = ((hue <= 15) | (hue >= 150)) if prefix == 'processing_' and color == 'red' else colors[color]
            result[prefix+color] = mask & (saturation > sat) & (value > light)
    result['white'] = (rgb.min(axis=2) > 190) & (rgb.max(axis=2)-rgb.min(axis=2) < 65)
    result['visible'] = value > 60
    return result


def read_chunks(root, manifest):
    count = 0
    for name in manifest['chunks']:
        with np.load(root/name, allow_pickle=False) as chunk:
            if list(chunk['fields']) != FIELDS or len(chunk['masks']) != len(chunk['times']):
                raise ValueError('Invalid native feature chunk')
            for packed, pts, time, fractions in zip(chunk['masks'], chunk['pts'], chunk['times'], chunk['fractions'], strict=True):
                masks = np.unpackbits(packed, axis=-1)[..., :FORMAT['width']].astype(bool)
                count += 1
                yield float(pts), float(time), dict(zip(FIELDS, masks, strict=True)), fractions.tolist()
    if count != manifest['frame_count']:
        raise ValueError('Native feature cache frame count differs')


def native_measurements(data, output, decoder):
    """Persist threshold measurements once; replay rules from bounded chunks.

    Mask thresholds are acquisition semantics. Changing them invalidates this
    cache; changing connected-component, body or event rules does not.
    """
    contract = {'format': FORMAT, 'source': source_contract(data)}
    root = output/'native-features'
    manifest_path = root/'manifest.json'
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        if manifest['contract'] == contract:
            with (output/'frames.jsonl').open() as stream:
                for raw, sample in zip_longest(stream, read_chunks(root, manifest)):
                    if raw is None or sample is None:
                        raise ValueError('Native feature cache differs from source frame count')
                    frame = json.loads(raw)
                    if abs(sample[0]-frame['source_pts_seconds']) > 1e-6 or abs(sample[1]-frame['playback_seconds']) > 1e-6:
                        raise ValueError('Native feature cache differs from source PTS')
                    yield sample
            return
    pending = output/'native-features.build'
    shutil.rmtree(pending, ignore_errors=True)
    pending.mkdir()
    before = Path(data['media']['path']).stat()
    chunks, masks, pts_values, times, scores = [], [], [], [], []
    count = 0
    def flush():
        name = f'{len(chunks):05}.npz'
        np.savez_compressed(pending/name, fields=FIELDS, masks=np.asarray(masks), pts=pts_values, times=times, fractions=scores)
        chunks.append(name)
        masks.clear(); pts_values.clear(); times.clear(); scores.clear()
    try:
        from piu_timeline.play.receptors import fractions
        decoded = decoder(data['media'], data['start_seconds'], data['end_seconds'], data['game_roi'], FORMAT['width'])
        for pts, time, rgb in decoded:
            planes = measurements(rgb)
            values = fractions(rgb, data['layout'])
            masks.append(np.packbits(np.stack([planes[key] for key in FIELDS]), axis=-1))
            pts_values.append(pts); times.append(time); scores.append(values); count += 1
            if len(masks) == FORMAT['chunk_frames']:
                flush()
            yield pts, time, planes, values
        if masks:
            flush()
        after = Path(data['media']['path']).stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Source changed during native feature acquisition')
        (pending/'manifest.json').write_text(json.dumps({'contract': contract, 'chunks': chunks, 'frame_count': count})+'\n')
        shutil.rmtree(root, ignore_errors=True)
        pending.replace(root)
    finally:
        shutil.rmtree(pending, ignore_errors=True)
