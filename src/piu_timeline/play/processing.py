"""Observe moving-head persistence at receptors without consulting the HUD or input light."""
from bisect import bisect_left
from collections import Counter
import json

import cv2
import numpy as np

PIXEL_FORMAT = {'schema': 1, 'width': 325, 'measurement': 'lane_color_white_and_visibility_masks',
                'receptor_band_spacing': [-1.6, 3.6]}
PROCESSING_FORMAT = {'schema': 1, 'revision': 3}


class ReceptorPixels:
    """Retain spatial pixels, not a lane brightness scalar, during native acquisition."""
    def __init__(self, layout, width, height):
        self.layout, self.width, self.height = layout, width, height
        self.spacing = float(np.median(np.diff([lane['x']*width for lane in layout['lanes']])))
        receptor = layout['receptor_y']*height
        self.top = max(0, int(receptor-1.6*self.spacing))
        self.bottom = min(height, int(receptor+3.6*self.spacing))
        self.half = max(3, round(.55*self.spacing))
        self.samples, self.times, self.pts = [], [], []

    def observe(self, rgb, pts, time):
        hue, saturation, value = cv2.split(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV))
        colors = {'blue': (hue >= 85) & (hue <= 130),
                  'red': (hue <= 15) | (hue >= 150), 'yellow': (hue >= 15) & (hue <= 45)}
        white = (rgb.min(axis=2)>190) & (rgb.max(axis=2)-rgb.min(axis=2)<65)
        masks = []
        for lane in self.layout['lanes']:
            x = round(lane['x']*self.width)
            mask = colors[lane['color']] & (saturation>90) & (value>140)
            padded = [np.pad(channel[self.top:self.bottom], ((0,0),(self.half,self.half)))
                      for channel in (mask, white, value>60)]
            masks.append(np.stack([p[:,x:x+2*self.half+1] for p in padded]))
        self.samples.append(np.packbits(np.stack(masks), axis=-1))
        self.times.append(time); self.pts.append(pts)

    def save(self, path, contract):
        temporary = path.with_suffix('.build-npz')
        try:
            with temporary.open('wb') as stream:
                np.savez_compressed(stream, masks=np.asarray(self.samples), times=self.times, pts=self.pts,
                                    top=self.top, half=self.half, height=self.height,
                                    contract=json.dumps({'format': PIXEL_FORMAT, 'source': contract}, sort_keys=True))
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def patch_at(mask, y, radius):
    center = round(y)
    if center-radius < 0 or center+radius >= mask.shape[0]:
        return None
    middle = mask.shape[1]//2
    return mask[center-radius:center+radius+1, middle-radius:middle+radius+1]


def overlap(template, image):
    total = int(template.sum())+int(image.sum())
    return 2*int((template & image).sum())/total if total else 0.


def transition(samples, receptor, spacing):
    """A disappearance is a visual event, never a successful judgment by itself."""
    present = [s for s in samples if s['state'] == 'present']
    if not present:
        return {'status': 'unresolved', 'reason': 'no_verified_head_template'}
    if sum(s['y'] < receptor-.65*spacing for s in present) >= 2:
        return {'status': 'passed_target', 'reason': 'head_observed_beyond_receptor'}
    last = present[-1]
    after = [s for s in samples if s['time'] > last['time']]
    absent = [s for s in after if s['state'] == 'absent']
    # A bounded flash may hide the transition. Clear observations on both
    # sides bracket it; later clear absence corroborates without narrowing it.
    blocked = any(s.get('unknown_reason') not in (None, 'white_effect', 'partial_shape')
                  for s in after if s['state'] == 'unknown' and (not absent or s['time'] <= absent[0]['time']))
    if (len(absent) >= 2 and len(present) >= 3 and not blocked
            and 0 < absent[0]['time']-last['time'] <= .075
            and 0 < absent[1]['time']-absent[0]['time'] <= .1
            and absent[1]['time']-last['time'] <= .15
            and -.45*spacing <= last['y']-receptor <= 1.25*spacing
            and absent[0]['y'] >= receptor-.8*spacing
            and all(0 < b['time']-a['time'] <= .05 for a,b in zip([last]+after,after))):
        return {'status': 'disappeared_near_receptor', 'reason': 'verified_head_then_clear_absence',
                'range': [last['time'], absent[0]['time']],
                'source_pts_seconds': [last['pts'], absent[0]['pts']],
                'confirmation_source_pts_seconds': absent[1]['pts']}
    return {'status': 'unresolved', 'reason': 'occlusion_gap_or_unobserved_transition'}


def observe_processing(data, path):
    """Compare each fitted head with its own approaching color silhouette.

    These observations depend on the motion identity, not combo, judgment or
    receptor-light decisions. Saturated white effects and HUD overlap are unknown.
    """
    if not path.is_file():
        return {'format': PROCESSING_FORMAT, 'available': False, 'notes': [], 'counts': {}}
    from piu_timeline.play.holds.features import feature_contract
    with np.load(path, allow_pickle=False) as saved:
        if json.loads(str(saved['contract'])) != {'format': PIXEL_FORMAT, 'source': feature_contract(data)}:
            raise ValueError('Processing pixels do not belong to this source/geometry contract')
        masks, columns = saved['masks'], 2*int(saved['half'])+1
        times, pts = saved['times'], saved['pts']
        top, height = int(saved['top']), int(saved['height'])
    scale = height/data.get('analysis_height', round(data['analysis_width']*data['game_roi'][3]/data['game_roi'][2]))
    spacing = float(np.median(np.diff([lane['x']*PIXEL_FORMAT['width'] for lane in data['layout']['lanes']])))
    receptor = data['layout']['receptor_y']*height
    radius = max(2, round(.45*spacing))
    # Cap identity is resolved before interpreting a disappearance as a tap.
    components = {n for h in data.get('hold_analysis', {}).get('holds', []) for n in h['covered_notes']}
    result = []
    for index, note in enumerate(data.get('notes', [])):
        record = {'note': index, 'lane': note['lane'], 'samples': []}
        if index in components:
            result.append({**record, 'status': 'hold_component', 'reason': 'use_sustained_body_state'}); continue
        if note['status'] != 'estimated':
            result.append({**record, 'status': 'unresolved', 'reason': 'unfitted_track'}); continue
        velocity = note.get('velocity_pixels_per_second', 0)*scale
        target = note.get('target_seconds')
        if velocity >= -spacing or target is None or note.get('prediction_uncertainty_seconds', 1) > .05:
            result.append({**record, 'status': 'unresolved', 'reason': 'unsupported_motion'}); continue
        def lane_mask(fi):
            return np.unpackbits(masks[fi, note['lane']], axis=-1)[..., :columns].astype(bool)
        templates = []
        for time, y in note.get('points', []):
            if not receptor+1.4*spacing <= y*scale <= receptor+2.8*spacing:
                continue
            fi = bisect_left(times, time-1e-6)
            if fi == len(times) or abs(times[fi]-time)>1e-6:
                continue
            color, white, _ = lane_mask(fi)
            template = patch_at(color, y*scale-top, radius)
            light = patch_at(white, y*scale-top, radius)
            if template is not None and light is not None and .12 < template.mean() < .85 and light.mean() < .45:
                templates.append(template)
        if len(templates) < 3:
            result.append({**record, 'status': 'unresolved', 'reason': 'insufficient_clear_approach'}); continue
        # Median silhouette retains repeatedly observed pixels and rejects animation noise.
        template = np.mean(templates, axis=0)>=.5
        start, end = target-min(.25, 2.8*spacing/-velocity), target+min(.2, 1.2*spacing/-velocity)
        from piu_timeline.play.holds.features import ui_regions
        regions = ui_regions(data['layout'])
        competing = any(other is not note and other['lane'] == note['lane'] and other.get('target_seconds') is not None
                        and abs(other['target_seconds']-target)*-velocity < .9*spacing
                        for other in data['notes'] if other['status'] == 'estimated')
        peers = [s for s in data.get('scroll_motion', {}).get('samples', []) if s['chunk'] == note.get('motion_chunk')]
        peer_times = [s['time'] for s in peers]
        for fi in range(bisect_left(times, start), bisect_left(times, end)):
            time, source_pts = float(times[fi]), float(pts[fi])
            y = receptor+velocity*(time-target)
            if peers:
                pi = bisect_left(peer_times, time)
                if pi >= len(peers) or abs(peers[pi]['time']-time)>1e-6:
                    continue
                y = receptor+(note['motion_target_phase']-peers[pi]['phase'])*scale
            state, score, reason = 'unknown', None, 'partial_shape'
            color, light, visibility = lane_mask(fi)
            image = patch_at(color, y-top, radius)
            white = patch_at(light, y-top, radius)
            x = data['layout']['lanes'][note['lane']]['x']
            hidden = any(rx <= x <= rx+rw and ry*height-radius <= y <= (ry+rh)*height+radius
                         for rx,ry,rw,rh in regions)
            if image is None or white is None:
                reason = 'image_boundary'
            elif competing:
                reason = 'competing_head'
            elif hidden:
                reason = 'hud_occlusion'
            elif visibility.mean()<=.015:
                reason = 'screen_not_visible'
            elif white.mean()>=.45:
                reason = 'white_effect'
            else:
                score = overlap(template, image)
                state = 'present' if score>=.65 else 'absent' if score<=.18 else 'unknown'
                if state == 'absent':
                    # Bloom can desaturate the colored head outside the strict
                    # white core. Its neighboring pixels are not clear absence.
                    halo_radius = max(1, round(.1*spacing))
                    halo = cv2.dilate(white.astype('uint8'), np.ones((2*halo_radius+1,2*halo_radius+1), dtype='uint8'))
                    if template.any() and halo[template].mean() >= .3:
                        state, reason = 'unknown', 'white_effect'
            record['samples'].append({'time': time, 'pts': source_pts, 'y': float(y), 'state': state, 'score': score,
                                      'unknown_reason': reason if state == 'unknown' else None})
        result.append({**record, **transition(record['samples'], receptor, spacing)})
    from piu_timeline.play.visibility import pre_receptor_losses
    boundaries = pre_receptor_losses(result, receptor, spacing)
    holds = [{'hold': h['id'], 'lane': h['lane'], 'start_range': h['start_range'],
              'end_range': h['end_range'], 'source_pts_range': h.get('source_pts_range'),
              'status': 'end_unresolved' if h['end_censored'] or not h['end_range'] else 'tail_crossing_supported'}
             for h in data.get('hold_analysis', {}).get('holds', [])]
    return {'format': PROCESSING_FORMAT, 'available': True, 'trace': 'processing-features.npz',
            'notes': result, 'holds': holds, 'visibility_boundaries': boundaries,
            'pixel_coordinates': {'width': PIXEL_FORMAT['width'], 'height': height, 'origin': 'game_crop_top_left'},
            'counts': dict(Counter(record['status'] for record in result)),
            'semantics': 'Observed disappearance is not a successful judgment or physical press. Unknown is retained.'}


def processing_support(data, note, lo, hi, guard=0):
    """Return the independently observed transition only when its bracket agrees."""
    for event in data.get('visual_channels', {}).get('processing', {}).get('notes', []):
        if event['note'] == note and event['status'] == 'disappeared_near_receptor':
            a, b = event['range']
            if a <= hi+guard and b >= lo-guard:
                return event
    return None


def processing_conflicts(data, note, lo, hi, guard=0):
    """A clear, distant disappearance contradicts a proposed display association."""
    guard = max(.075, guard)
    return any(event['note'] == note and event['status'] == 'disappeared_near_receptor'
               and (event['range'][1] < lo-guard or event['range'][0] > hi+guard)
               for event in data.get('visual_channels', {}).get('processing', {}).get('notes', []))
