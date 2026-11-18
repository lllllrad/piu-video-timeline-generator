"""Inspect dense cap strips with existing skin references on consecutive source frames."""
import json

import cv2
import numpy as np

from piu_timeline.play.frames import decode_frames
from piu_timeline.play.observations.skin_results import publish, restore
from piu_timeline.play.skins.detector import SkinDetector, occluded_support
from piu_timeline.play.skins.frame_centers import FrameCenters
from piu_timeline.play.skins.localization_pixels import measure
from piu_timeline.play.skins.overlap import runs
from piu_timeline.play.skins.sampling import key

FORMAT = {'schema': 1, 'method': 'persistent_positive_cap_strip', 'strip_height_pixels': 8,
          'minimum_cap_fraction': .2, 'maximum_error_fraction': .35,
          'maximum_step_pixels': 4, 'minimum_stack_heads': 3}


def candidates(detector, image, lane):
    """Search horizontal bands of supported cap pixels, retaining measured pixels only."""
    best = {}
    band_height = FORMAT['strip_height_pixels']
    for template in detector.templates:
        if template['role'] == 'hold_body' or template['lane_kind'] != lane % 5:
            continue
        bounds = detector.search_bounds(detector.layout['lanes'][lane], template)
        if bounds is None:
            continue
        left, top, right, bottom = bounds
        height, width = template['mask'].shape
        ax, ay = template['anchor']
        cap = next(region for region in template['regions'] if region['name']=='cap')
        a, b, c, d = cap['box']
        support = cap['mask'].astype('float32')
        limit = cap.get('maximum_error', .015)
        for lo in range(d-b-band_height+1):
            hi = lo+band_height
            mask = support[lo:hi]
            count = int(mask.sum())
            ref = template['rgb'][b+lo:b+hi,a:c]
            if count < FORMAT['minimum_cap_fraction']*support.sum() or np.ptp(ref[mask.astype(bool)]) < .2:
                continue
            area = image[top+b+lo:bottom-height+b+hi,left+a:right-width+c]
            values = np.maximum(cv2.matchTemplate(area,ref,cv2.TM_SQDIFF,mask=mask),0)/(3*count)
            rows, cols = np.nonzero(values <= FORMAT['maximum_error_fraction']*limit)
            for row, col in zip(rows,cols,strict=True):
                x, y = left+int(col), top+int(row)
                anchor = y+ay
                if anchor > detector.layout.get('note_y_max', .95)*detector.height:
                    continue
                if occluded_support(detector.layout, mask, x+a, y+b+lo, detector.width, detector.height):
                    continue
                error = float(values[row,col])
                score = error/limit
                if anchor in best and best[anchor][0] <= score:
                    continue
                pixels = np.zeros((height,width),bool)
                pixels[b+lo:b+hi,a:c] = mask
                record = {'lane':lane, 'x':(x+ax)/detector.width, 'y':anchor/detector.height,
                          'role':'unknown', 'template_role':template['role'], 'template':template['id'],
                          'quality':1-score, 'classification_status':'cap_only',
                          'reason':'skin_image_persistent_visible_cap_strip', 'method':'skin_image',
                          'skin':detector.bank['skin'], 'bounds_pixels':[x,y,x+width,y+height],
                          'region_errors':{'cap':error}, 'visible_cap_runs':runs(pixels),
                          'partial_cap_evidence':{'format':FORMAT,'compared_pixels':count},
                          **{k:template[k] for k in ('sampling_phase_pixels','reference_scale_y',
                              'sampling_kernel','sampling_origin_pixels') if k in template}}
                best[anchor] = score,record
    selected = []
    for y,(_,record) in sorted(best.items(),key=lambda entry:entry[1][0]):
        if all(abs(y-cap['y']*detector.height)>=detector.same_anchor_pixels for cap in selected):
            record['cap_localization'] = measure(image,detector.by_sampling[key(record)],record)
            selected.append(record)
    return sorted(selected,key=lambda cap:cap['y'])


def persistent(neighbor_frames, height):
    """Require unique, positive cap matches in three original adjacent frames."""
    before, current, after = neighbor_frames
    pairs = []
    limit = FORMAT['maximum_step_pixels']/height
    for head in current:
        peers = [[cap for cap in adjacent if abs(head['y']-cap['y'])<=limit]
                 for adjacent in (before,after)]
        if any(len(group)!=1 for group in peers):
            continue
        if all(sum(abs(cap['y']-group[0]['y'])<=limit for cap in current)==1 for group in peers):
            pairs.append(head)
    return pairs if len(pairs)>=FORMAT['minimum_stack_heads'] else []


def recheck(data, directory, bank, start, end, lane):
    if bank['contract'] != data['skin_detector']['contract']['bank']:
        raise ValueError('The recheck skin bank differs from the acquired observations')
    detector = SkinDetector(bank,data['layout'],data['analysis_width'],data['analysis_height'])
    centers = FrameCenters(detector)
    frames = [(pts,t,rgb.astype('float32')/255) for pts,t,rgb in
              decode_frames(data['media'],max(data['start_seconds'],start-.05),
                            min(data['end_seconds'],end+.05),data['game_roi'],data['analysis_width'])]
    observed = [candidates(detector,image,lane) for pts,t,image in frames]
    updates = {}
    for i,(pts,t,_) in enumerate(frames[1:-1],1):
        if start<=t<end and all(0<frames[j+1][0]-frames[j][0]<=.05 for j in (i-1,i)):
            supported = persistent(observed[i-1:i+2],detector.height)
            if supported:
                witness = [frames[j][0] for j in (i-1,i,i+1)]
                for cap in supported:
                    cap['partial_cap_evidence']['source_pts_seconds'] = witness
                updates[t] = pts,supported
    trace = directory/'frames.jsonl'
    temporary = directory/'frames.partial-caps.pending'
    count = 0
    try:
        with trace.open() as source, temporary.open('w') as target:
            for line in source:
                frame = json.loads(line)
                t = frame['playback_seconds']
                if t not in updates or any(n['lane']==lane for n in frame['notes']):
                    target.write(line)
                    continue
                pts, additions = updates[t]
                if pts != frame['source_pts_seconds']:
                    raise ValueError('Partial cap recheck differs from saved frame PTS')
                raw = restore(frame,directory)
                raw['skin_observations'].extend(additions)
                combined = publish(raw,directory,centers)
                original_count = len(frame['notes'])
                for note in combined['notes'][original_count:]:
                    position = note['position_result']
                    position['center'] = None
                    measurement = position['measurement']
                    measurement['native_cap_registration_status'] = 'partial_cap_unqualified_coordinate'
                    for field in ('native_cap_coordinate_uncertainty_pixels','native_cap_reference_template'):
                        measurement.pop(field,None)
                combined['notes'][:original_count] = frame['notes']
                combined['skin_observations'][:len(frame['skin_observations'])] = frame['skin_observations']
                target.write(json.dumps(combined)+'\n')
                count += len(additions)
        temporary.replace(trace)
    finally:
        temporary.unlink(missing_ok=True)
    return count
