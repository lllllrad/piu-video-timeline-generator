"""Recheck a visible dense cap against the selected skin's possible hold roles."""
import json

import numpy as np

from piu_timeline.play.frames import decode_frames
from piu_timeline.play.observations.skin_results import restore
from piu_timeline.play.screen_regions import note_occluders
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.overlap import positive_pixels, runs
from piu_timeline.play.skins.sampling import key

FORMAT = {'schema': 1, 'method': 'exposed_tap_cap_excludes_hold_variants',
          'anchor_radius_pixels': 1, 'minimum_distinguishing_pixels': 12}


def proof(detector, image, head, hidden):
    if (head['role'] != 'unknown' or head.get('classification_status') != 'cap_only'
            or not head.get('occlusion_evidence')):
        return None
    taps = [p for p in (head, *head.get('alternatives', []))
            if p.get('template_role', p['role']) == 'tap'
            and p.get('region_errors', {}).get('cap') is not None]
    if not taps:
        return None
    candidate = {**head, **min(taps, key=lambda p: p['region_errors']['cap'])}
    template = detector.by_sampling[key(candidate)]
    cap = next(r for r in template['regions'] if r['name'] == 'cap')
    if candidate['region_errors']['cap'] > cap.get('maximum_error', .015):
        return None
    a, b, c, d = candidate['bounds_pixels']
    visible = positive_pixels(image, template, candidate) & ~hidden[b:d,a:c]
    gx, gy = candidate['x'] * detector.width, candidate['y'] * detector.height
    counts = {'hold_start': 0, 'hold_end': 0}
    minimum = None
    witness = np.zeros_like(visible)
    for alternative in detector.templates:
        role = alternative['role']
        if role not in counts or alternative['lane_kind'] != head['lane'] % 5:
            continue
        ax, ay = alternative['anchor']
        hh, ww = alternative['cap_support'].shape
        region = next(r for r in alternative['regions'] if r['name'] == 'cap')
        threshold = region.get('maximum_error', .015)
        for dx in range(-FORMAT['anchor_radius_pixels'], FORMAT['anchor_radius_pixels']+1):
            for dy in range(-FORMAT['anchor_radius_pixels'], FORMAT['anchor_radius_pixels']+1):
                left, top = round(gx-ax)+dx, round(gy-ay)+dy
                x, y, z, w = max(a,left), max(b,top), min(c,left+ww), min(d,top+hh)
                if x >= z or y >= w:
                    return None
                tap_slice = np.s_[y-b:w-b,x-a:z-a]
                hold_slice = np.s_[y-top:w-top,x-left:z-left]
                expected = alternative['rgb'][hold_slice]
                distinguish = (visible[tap_slice] & alternative['cap_support'][hold_slice]
                               & (np.square(template['rgb'][tap_slice]-expected).mean(axis=2)>4*threshold))
                pixels = int(distinguish.sum())
                if (pixels < FORMAT['minimum_distinguishing_pixels']
                        or np.square((image[y:w,x:z]-expected)[distinguish]).mean() <= threshold):
                    return None
                counts[role] += 1
                minimum = pixels if minimum is None else min(pixels, minimum)
                witness[tap_slice] |= distinguish
    if not all(counts.values()):
        return None
    return {'format': FORMAT, 'template': candidate['template'], 'bounds_pixels': [a,b,c,d],
            'cap_error': candidate['region_errors']['cap'], 'hold_variants_excluded': counts,
            'minimum_distinguishing_pixels': minimum, 'distinguishing_runs': runs(witness)}


def recheck(data, directory, bank, start, end, lane):
    """Add independent type proofs to a scratch trace while preserving its measured positions."""
    if bank['contract'] != data['skin_detector']['contract']['bank']:
        raise ValueError('The recheck skin bank differs from the acquired observations')
    detector = SkinDetector(bank, data['layout'], data['analysis_width'], data['analysis_height'])
    frames = iter(decode_frames(data['media'], start, end, data['game_roi'], data['analysis_width']))
    trace = directory/'frames.jsonl'
    pending = directory/'frames.tap-recheck.pending'
    count = 0
    try:
        next_frame = next(frames, None)
        with trace.open() as source, pending.open('w') as target:
            for line in source:
                f = json.loads(line)
                t = f['playback_seconds']
                if not start <= t < end:
                    target.write(line)
                    continue
                if next_frame is None or next_frame[:2] != (f['source_pts_seconds'], t):
                    raise ValueError('Tap recheck frames differ from the original PTS')
                image = next_frame[2].astype(np.float32)/255
                heads = [(i,h) for i,h in enumerate(restore(f,directory)['skin_observations']) if h['role']!='hold_body']
                planes = {}
                for i,h in heads:
                    a,b,c,d = h['bounds_pixels']
                    plane = np.zeros(image.shape[:2],bool)
                    plane[b:d,a:c] = positive_pixels(image, detector.by_sampling[key(h)], h)
                    planes[i] = plane
                total = np.sum(list(planes.values()),axis=0) if planes else np.zeros(image.shape[:2],int)
                hud = np.zeros(image.shape[:2],bool)
                for region in note_occluders(data['layout']):
                    x,y,w,z = region['rect']
                    hud[int(y*detector.height):int((y+z)*detector.height+.999),
                        int(x*detector.width):int((x+w)*detector.width+.999)] = True
                for i,h in heads:
                    saved = f['skin_observations'][i]
                    if h['lane'] != lane or saved.get('tap_cap_evidence'):
                        continue
                    result = proof(detector,image,h,hud|((total-planes[i])>0))
                    if result:
                        saved['tap_cap_evidence'] = result
                        count += 1
                target.write(json.dumps(f)+'\n')
                next_frame = next(frames,None)
        if next_frame is not None:
            raise ValueError('Tap recheck produced frames outside the saved trace')
        pending.replace(trace)
    finally:
        frames.close()
        pending.unlink(missing_ok=True)
    return count
