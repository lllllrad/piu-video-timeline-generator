"""Declared Phoenix receptor positions relative to the full game image."""
import re
import json
import math

import cv2
import numpy as np

from piu_timeline.play.frames import decode_frames
from piu_timeline.metadata.recognition import capture_game


RECEPTOR_Y = .142
SINGLE_X = {
    'p1': (.195, .254, .313, .372, .431),
    'p2': (.570, .629, .688, .747, .806),
}
DOUBLE_X = (.235, .29423, .35346, .41269, .47135,
            .52962, .58885, .64808, .7075, .76654)
COLORS = ('blue', 'red', 'yellow', 'red', 'blue')
NAMES = ('DL', 'UL', 'C', 'UR', 'DR')


def fixed_layout(segment, player=None):
    """Select a declared layout, without claiming image-detected receptors.

    The game ROI must be the full, unmirrored game image. Single requires a
    known player side; missing mode/side uses the visual/manual fallback.
    """
    chart = segment.get('chart') or ''
    if re.fullmatch(r'(?:D|HD)\d{1,2}', chart):
        xs, profile = DOUBLE_X, 'double'
    elif re.fullmatch(r'(?:S|HS)\d{1,2}|VERY HARD \d{1,2}', chart):
        players = segment.get('players', {})
        side = player or (next(iter(players)) if len(players) == 1 else None)
        if side not in SINGLE_X:
            return None
        xs, profile = SINGLE_X[side], 'single_'+side
    else:
        return None
    middle = sum(xs)/len(xs)
    return {'method': 'fixed_phoenix_game_layout', 'profile': profile, 'profile_revision': 1,
            'receptor_y': RECEPTOR_Y, 'note_y_max': .95,
            'combo_roi': [middle-.07, .52, .14, .075],
            'lanes': [{'x': x, 'color': COLORS[index % 5],
                       'name': f'{index//5+1}:{NAMES[index % 5]}'} for index, x in enumerate(xs)]}


def validate_layout(layout):
    if not isinstance(layout, dict) or not isinstance(layout.get('lanes'), list) or len(layout['lanes']) not in (5, 10):
        raise ValueError('Layout needs 5 or 10 ordered lanes')
    xs = []
    for lane in layout['lanes']:
        x = lane.get('x')
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 < x < 1:
            raise ValueError('Lane x must be a finite game-relative fraction')
        if lane.get('color') not in COLORS:
            raise ValueError('Lane color must be blue, red or yellow')
        xs.append(x)
    if any(b - a < .01 for a, b in zip(xs, xs[1:])):
        raise ValueError('Lane centers must be ordered and separated')
    receptor = layout.get('receptor_y')
    bottom = layout.get('note_y_max', .95)
    if not isinstance(receptor, (int, float)) or not isinstance(bottom, (int, float)) or not 0 < receptor < bottom < 1:
        raise ValueError('Layout needs 0 < receptor_y < note_y_max < 1')
    for name in ('combo_roi','judgment_roi'):
        if name=='judgment_roi' and name not in layout:
            continue
        region=layout.get(name,[])
        if len(region)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in region):
            raise ValueError(f'{name} needs four finite fractions')
        x,y,w,h=region
        if not (0<=x<x+w<=1 and 0<=y<y+h<=1):
            raise ValueError(f'{name} must fit inside the game image')
    return layout


def receptor_centers(rgb):
    height, width = rgb.shape[:2]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = ((hsv[:, :, 1] < 65) & (hsv[:, :, 2] > 160)).astype('uint8') * 255
    mask[:int(height * .065)] = 0; mask[int(height * .23):] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if .035 * width < w < .09 * width and .05 * height < h < .15 * height:
            candidates.append((x + w / 2, y + h / 2))
    groups = []
    for x, y in sorted(candidates):
        if groups and x - np.mean([p[0] for p in groups[-1]]) < .012 * width:
            groups[-1].append((x, y))
        else:
            groups.append([(x, y)])
    centers = [(float(np.median([p[0] for p in g])), float(np.median([p[1] for p in g]))) for g in groups]
    return centers


def locate_layout(rgb, chart, player=None, centers=None):
    height, width = rgb.shape[:2]
    centers = receptor_centers(rgb) if centers is None else centers
    expected = (10 if str(chart).startswith(('D', 'HD')) else 5) if chart else None
    if len(centers) == 10 and expected == 5 and player:
        centers = centers[:5] if player == 'p1' else centers[5:]
    if len(centers) not in ((expected,) if expected else (5, 10)):
        raise ValueError(f'Found {len(centers)} receptor centers, expected {expected or '5 or 10'}; provide --layout JSON after reviewing preview.png')
    spacing = np.diff([p[0] for p in centers])
    if np.std(spacing) / np.mean(spacing) > .15 or np.std([p[1] for p in centers]) > height * .025:
        raise ValueError('Receptor geometry is ambiguous; provide --layout JSON')
    middle = float(np.mean([p[0] for p in centers])) / width
    return validate_layout({'method': 'observed_receptor_outlines',
                            'receptor_y': float(np.median([p[1] for p in centers])) / height,
                            'note_y_max': .95, 'combo_roi': [middle - .07, .52, .14, .075],
                            'lanes': [{'x': x / width, 'color': COLORS[i % 5],
                                       'name': f'{i // 5 + 1}:{NAMES[i % 5]}'} for i, (x, _) in enumerate(centers)]})



def combine_receptor_observations(seen, width, height, expected=None):
    """Recover only receivers observed in at least two distinct native frames."""
    groups = []
    for centers, observation in seen:
        pts = observation.get('source_pts_seconds')
        if pts is None:
            continue
        for x, y in centers:
            compatible = [group for group in groups
                          if abs(x-np.median([p[0] for p in group])) < .008*width
                          and abs(y-np.median([p[1] for p in group])) < .012*height]
            if len(compatible) == 1:
                compatible[0].append((x,y,pts))
            elif not compatible:
                groups.append([(x,y,pts)])
    stable = sorted((float(np.median([p[0] for p in group])),float(np.median([p[1] for p in group])))
                    for group in groups if len({p[2] for p in group}) >= 2)
    choices = []
    for count in ((expected,) if expected else (10,5)):
        for begin in range(len(stable)-count+1):
            centers = stable[begin:begin+count]
            spacing = np.diff([p[0] for p in centers])
            if (np.std(spacing)/np.mean(spacing) <= .10
                    and np.std([p[1] for p in centers]) <= height*.012):
                choices.append(centers)
        if choices:
            break
    # Two competing grids cannot be resolved by choosing a convenient one.
    return choices[0] if len(choices) == 1 else None


def recover_layout(record, roi, segment, preview, rgb, calibration, player=None):
    """Require agreement across source frames; recover receivers hidden by flashes."""
    fixed = fixed_layout(segment, player)
    if fixed is not None:
        calibration['geometry_basis'] = {'kind': 'declared_game_layout',
                                         'profile': fixed['profile'], 'revision': fixed['profile_revision']}
        return validate_layout(fixed)
    from piu_timeline.play.layout_evidence import MovingHeadProfiles
    moving_heads = MovingHeadProfiles(segment, player)
    candidates, seen, images, observations = [], [], [rgb], [dict(calibration)]
    expected = (10 if str(segment['chart']).startswith(('D','HD')) else 5) if segment.get('chart') else None
    for saved_path in sorted(preview.parent.parent.glob('segment-*/analysis.json')):
        if not re.fullmatch(r'segment-\d{3}', saved_path.parent.name):
            continue
        saved = json.loads(saved_path.read_text())
        if saved.get('media') != record or saved.get('game_roi') != list(roi):
            continue
        candidate = saved.get('layout')
        if candidate and (expected is None or len(candidate['lanes']) == expected):
            candidates.append((candidate, {'source_pts_seconds': None, 'shared_from': str(saved_path)}))

    def observe(image, observation):
        declared = moving_heads.observe(image, observation)
        if declared is not None:
            calibration['geometry_basis'] = {'kind':'declared_layout_with_observed_moving_heads',
                                             'profile':declared['profile'], 'support':declared['geometry_support']}
            return validate_layout(declared)
        centers = receptor_centers(image)
        seen.append((centers, observation))
        try:
            candidates.append((locate_layout(image, segment.get('chart'), player), observation))
        except ValueError:
            pass
        height,width = image.shape[:2]
        for candidate,source in candidates:
            xs = [lane['x'] for lane in candidate['lanes']]
            for points,other_source in seen:
                if source.get('source_pts_seconds') == other_source.get('source_pts_seconds'):
                    continue
                matched = {min(range(len(xs)),key=lambda i:abs(xs[i]-x/width))
                           for x,y in points if abs(y/height-candidate['receptor_y'])<.012
                           and min(abs(x/width-cx) for cx in xs)<.008}
                if len(matched)>=min(4,len(xs)) and max(matched)-min(matched)>=len(xs)//2:
                    result = dict(candidate)
                    result['method'] = 'corroborated_shared_geometry' if source.get('shared_from') else 'corroborated_receptor_outlines'
                    if source.get('shared_from'):
                        calibration['geometry_reference'] = source['shared_from']
                    return result
        combined = combine_receptor_observations(seen, width, height, expected)
        if combined is not None:
            try:
                result = locate_layout(image, segment.get('chart'), player, centers=combined)
                result['method'] = 'corroborated_partial_receptor_outlines'
                return result
            except ValueError:
                pass
        return None

    layout = observe(rgb, calibration)
    if layout is not None:
        calibration['supporting_frames'] = observations
        return layout
    directory = preview.parent / 'calibration'; directory.mkdir(exist_ok=True)
    offsets = (.5, 1.5, 3, 5, 8, 13, 21, 34)
    for index, offset in enumerate(offsets):
        seconds = min(segment['start_seconds'] + offset, segment['end_seconds'] - .1)
        path = directory / f'source-{index:02}.png'
        observation = capture_game(record, path, seconds, roi)
        image = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        images.append(image); observations.append(observation)
        layout = observe(image, observation)
        if layout is not None:
            calibration['supporting_frames'] = observations
            return layout
    # Widely spaced integer-second samples can repeatedly hit the same beat
    # flash. Observe distinct native frames in a short off-phase window before
    # taking a median that may erase every receiver it was meant to reveal.
    support = moving_heads.latest_support()
    anchor = segment['start_seconds']+3 if support is None else support-record.get('container_start_seconds',0)
    window_start = min(max(segment['start_seconds'],anchor+.137), segment['end_seconds']-.1)
    window_end = min(window_start+.8, segment['end_seconds'])
    for index,(pts,seconds,image) in enumerate(decode_frames(record,window_start,window_end,roi,rgb.shape[1])):
        if index % 3:
            continue
        path = directory / f'native-{index:02}.png'
        cv2.imwrite(str(path),cv2.cvtColor(image,cv2.COLOR_RGB2BGR))
        observation = {'source_pts_seconds':pts,'playback_seconds':seconds,'roi':list(roi),'file':str(path)}
        observations.append(observation)
        layout = observe(image,observation)
        if layout is not None:
            calibration['supporting_frames'] = observations
            return layout
    # Flash positions move while the static receiver outlines stay in place.
    median = np.median(np.stack(images), axis=0).astype('uint8')
    layout = locate_layout(median, segment.get('chart'), player)
    layout['method'] = 'temporal_median_receptor_outlines'
    cv2.imwrite(str(directory / 'median.png'), cv2.cvtColor(median, cv2.COLOR_RGB2BGR))
    calibration['supporting_frames'] = observations
    return layout
