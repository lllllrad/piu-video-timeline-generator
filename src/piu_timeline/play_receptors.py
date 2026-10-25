"""Native receptor measurements and common-flash rejection, without OCR."""
from hashlib import sha256
from itertools import zip_longest
import json
from pathlib import Path

import numpy as np

from .play_frames import decode_frames

FORMAT = {'schema': 1, 'width': 325, 'measurement': 'white_fraction_190_65'}


def onset_overlaps(run, lo, hi, guard=0):
    """Require a bounded, observed off-to-on transition, not persistent light."""
    if run['lit'] is not True or run['frames'] + run.get('corroborating_lit_frames_after_flash', 0) < 2:
        return False
    if 'onset_range' in run:
        interval = run['onset_range']
    else:
        # Legacy runs have no bridge provenance; only adjacent known states count.
        interval = ([run['previous_seconds'], run['start_seconds']]
                    if run.get('previous_lit', False) is False and run.get('previous_seconds') is not None else None)
    return interval is not None and interval[0] <= hi+guard and interval[1] >= lo-guard


def fractions(rgb, layout, full_height=None, y_offset=0):
    height = full_height or rgb.shape[0]
    width = rgb.shape[1]
    spacing = float(np.median(np.diff([lane['x']*width for lane in layout['lanes']])))
    receptor = layout['receptor_y']*height
    white = (rgb.min(axis=2)>190) & (rgb.max(axis=2)-rgb.min(axis=2)<65)
    result = []
    for lane in layout['lanes']:
        x = lane['x']*width
        left, right = max(0, int(x-.28*spacing)), min(width, int(x+.28*spacing))
        top, bottom = max(0, int(receptor-.28*spacing))-y_offset, min(height, int(receptor+.28*spacing))-y_offset
        result.append(float(white[top:bottom, left:right].mean()))
    return result


def observations(data, directory, frames):
    """Top up legacy bool-only caches once using only the native receptor strip."""
    if all('receptor_white_fraction' in frame for frame in frames):
        return np.asarray([frame['receptor_white_fraction'] for frame in frames])
    # Synthetic/legacy observations without a verified stream remain unchanged.
    if not data.get('media', {}).get('video_streams'):
        return None
    contract = {'format': FORMAT, **{key:data[key] for key in ('media','start_seconds','end_seconds','game_roi','layout')},
                'timestamps':sha256(json.dumps([(f['source_pts_seconds'],f['playback_seconds']) for f in frames]).encode()).hexdigest()}
    path = directory/'receptor-features.npz'
    if path.is_file():
        with np.load(path, allow_pickle=False) as saved:
            if json.loads(str(saved['contract'])) == contract:
                scores = saved['fractions']
                if scores.shape != (len(frames),len(data['layout']['lanes'])):
                    raise ValueError('Receptor feature dimensions differ from native observations')
                return scores
    print('  Extracting native receptor strip measurements; no OCR...', flush=True)
    width = FORMAT['width']; height = round(width*data['game_roi'][3]/data['game_roi'][2])
    spacing = float(np.median(np.diff([lane['x']*width for lane in data['layout']['lanes']])))
    # Cover exact integer boundaries used by the full-frame measurement.
    top = max(0,int(data['layout']['receptor_y']*height-.28*spacing))
    bottom = min(height,int(data['layout']['receptor_y']*height+.28*spacing))
    region = [0,top/height,1,(bottom-top)/height]
    # Floating region multiplication can round below the intended integer crop.
    region[1] = np.nextafter(region[1],1).item()
    region[3] = np.nextafter(bottom/height,1).item()-region[1]
    decoded = decode_frames(data['media'],data['start_seconds'],data['end_seconds'],data['game_roi'],width,region=region)
    before = Path(data['media']['path']).stat(); scores=[]
    for previous, item in zip_longest(frames,decoded):
        if previous is None or item is None:
            raise ValueError('Receptor feature count differs from native observations')
        pts,time,rgb = item
        if abs(pts-previous['source_pts_seconds'])>1e-6 or abs(time-previous['playback_seconds'])>1e-6:
            raise ValueError('Receptor feature PTS differs from native observations')
        scores.append(fractions(rgb,data['layout'],height,top))
    after = Path(data['media']['path']).stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('Source changed during receptor acquisition')
    scores=np.asarray(scores,dtype='float32')
    temporary=path.with_suffix('.build-npz')
    try:
        with temporary.open('wb') as stream:
            np.savez_compressed(stream,contract=json.dumps(contract,sort_keys=True),fractions=scores)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return scores


def reject_common_flashes(frames, scores):
    """Shared receptor whitening is unknown, rather than a press on every lane.

    Keep strong lane-local light above the shared level, including its trailing
    frames. Unknown samples alone cannot establish an independent input onset.
    """
    if scores is None:
        return frames
    result=[]; common=False
    for frame, values in zip(frames,scores,strict=True):
        baseline=float(np.median(values))
        threshold = len(values) if len(values)<=5 else len(values)-2
        if sum(value>.55 for value in values)>=threshold:
            common=True
        elif baseline<.25:
            common=False
        state=[bool(value>.55) for value in values]
        if common:
            state=[True if value>max(.55,baseline+.2) else False if value<.25 else None for value in values]
        result.append({**frame,'receptor_lit':state,'common_receptor_flash':common,
                       'receptor_white_fraction': [float(value) for value in values]})
    return result
