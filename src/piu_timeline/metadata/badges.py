"""Read observed circular chart badges as separate mode and numeral regions."""
from pathlib import Path
from hashlib import sha256
import re

import cv2
import numpy as np

from piu_timeline.vision.ocr import ocr_images

FORMAT = {'schema': 1, 'revision': 1, 'number_reader': 'known_line_with_pixel_variants'}


def badge_regions(image, phase, lines):
    """Locate circles in badge columns; summary rows require observed ordinals."""
    from piu_timeline.metadata.recognition import center, ordinal_number
    if phase not in ('result', 'summary'):
        return []
    height, width = image.shape[:2]
    scale = 1300/width
    gray = cv2.cvtColor(cv2.resize(image, (1300, round(height*scale))), cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(cv2.GaussianBlur(gray, (5, 5), 1), cv2.HOUGH_GRADIENT,
                              dp=1, minDist=60, param1=100, param2=32, minRadius=30, maxRadius=55)
    if circles is None:
        return []
    ordinals = {(ordinal_number(line['text']), round(center(line)[1], 3)) for line in lines
                if ordinal_number(line['text']) is not None and .4 < center(line)[0] < .6}
    result = []
    for x, y, radius in circles[0]/scale:
        cx, cy = x/width, y/height
        if phase == 'result':
            valid = (.25 < cx < .43 or .57 < cx < .77) and .25 < cy < .4
            stage = None
        else:
            valid = (.15 < cx < .35 or .65 < cx < .9) and .13 < cy < .94
            nearby = sorted((abs(cy-oy), stage) for stage, oy in ordinals)
            if not nearby or nearby[0][0] > .075:
                continue
            stage = nearby[0][1]
            if any(other != stage and distance-nearby[0][0] < .015 for distance, other in nearby[1:]):
                continue
        if not valid:
            continue
        left, top = max(0, round(x-radius*1.15)), max(0, round(y-radius*1.15))
        right, bottom = min(width, round(x+radius*1.15)), min(height, round(y+radius*1.15))
        result.append({'pixels': [left, top, right-left, bottom-top],
                       'player_id': 'p1' if cx < .5 else 'p2', 'stage': stage})
    return sorted(result, key=lambda item: (item['pixels'][1], item['pixels'][0]))


def read_badges(frame, phase, lines):
    """Keep raw pixels and a white-text variant as one source observation.

    The detector can miss large stylized numerals while reading the tiny mode
    caption. Read the known numeric strip directly, without text detection.
    Agreement between preprocessing variants is not multi-frame confirmation.
    """
    from piu_timeline.metadata.recognition import chart_mode, center
    frame = Path(frame)
    image = cv2.imread(str(frame))
    if image is None:
        raise ValueError(f'Cannot read chart badge source: {frame}')
    height, width = image.shape[:2]
    regions = badge_regions(image, phase, lines)
    source_key = sha256(frame.read_bytes()).hexdigest()[:16]
    paths = []
    for index, region in enumerate(regions):
        x, y, w, h = region['pixels']
        path = frame.with_name(frame.stem+f'-badge-v1-{source_key}-{phase}-{index}-whole.png')
        if not path.exists():
            cv2.imwrite(str(path), cv2.resize(image[y:y+h, x:x+w], None, fx=4, fy=4))
        paths.append(path)
    pending, number_paths = [], []
    for index, (region, path, observation) in enumerate(zip(regions, paths, ocr_images(paths, english=True))):
        modes = [line for line in observation['lines'] if chart_mode(line['text']) and line['confidence'] >= .75]
        if len({chart_mode(line['text']) for line in modes}) != 1:
            continue
        mode = max(modes, key=lambda line: line['confidence'])
        crop = cv2.imread(str(path))
        ch, cw = crop.shape[:2]
        bx, by, bw, bh = mode['box'];cx = center(mode)[0]*cw
        left, right = max(0, round(cx-bw*cw*.85)), min(cw, round(cx+bw*cw*.85))
        top, bottom = round((by+bh)*ch), min(ch, round((by+bh)*ch+bh*ch*3.1))
        digits = crop[top:bottom, left:right]
        if not digits.size:
            continue
        mask = (digits.min(axis=2) > 175) & (digits.max(axis=2)-digits.min(axis=2) < 70)
        if not .02 < mask.mean() < .7:
            continue
        region_key = f'{left}-{top}-{right}-{bottom}'
        raw = path.with_name(path.stem+f'-{region_key}-number.png')
        binary = path.with_name(path.stem+f'-{region_key}-number-white.png')
        isolated = np.repeat((255-mask.astype('uint8')*255)[..., None], 3, axis=2)
        isolated = cv2.copyMakeBorder(isolated, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        if not raw.exists():
            cv2.imwrite(str(raw), digits)
        if not binary.exists():
            cv2.imwrite(str(binary), isolated)
        number_paths.extend([raw, binary])
        pending.append((region, path, mode, [left/cw, top/ch, (right-left)/cw, (bottom-top)/ch], raw, binary))
    numbers = ocr_images(number_paths, english=True, single_line=True)
    result = []
    for index, (region, path, mode, digits_box, raw, binary) in enumerate(pending):
        variants = []
        for observation in numbers[index*2:index*2+2]:
            readings = [line for line in observation['lines'] if re.fullmatch(r'\d{1,2}', line['text'].strip())
                        and 1 <= int(line['text']) <= 99 and line['confidence'] >= .8]
            if len({int(line['text']) for line in readings}) != 1:
                break
            variants.append(max(readings, key=lambda line: line['confidence']))
        if len(variants) != 2 or int(variants[0]['text']) != int(variants[1]['text']):
            continue
        x, y, w, h = region['pixels']
        bounds = [x/width, y/height, w/width, h/height]
        common = {'badge_read': True, 'badge_id': str(path), 'badge_bounds': bounds,
                  'badge_stage': region['stage'], 'player_id': region['player_id'],
                  'method': 'segmented_chart_badge', 'badge_format': FORMAT}
        for line, box, source in ((mode, mode['box'], path),
                                  ({'text': str(int(variants[0]['text'])),
                                    'confidence': min(v['confidence'] for v in variants)}, digits_box, raw)):
            bx, by, bw, bh = box
            result.append({**line, **common, 'box': [(x+bx*w)/width, (y+by*h)/height, bw*w/width, bh*h/height],
                           'image': str(source), 'pixel_variants': [str(raw), str(binary)]})
    return result


def prefer_badges(lines):
    """Prefer complete region reads without erasing conflicting raw observations."""
    from piu_timeline.metadata.recognition import center, chart_mode
    direct = [line for line in lines if line.get('badge_read')]
    bounds = {tuple(line['badge_bounds']) for line in direct}
    result = []
    for line in lines:
        cx, cy = center(line)
        chart_glyph = chart_mode(line['text']) is not None or re.fullmatch(r'\d{1,2}', line['text'].strip())
        covered = any(x <= cx <= x+w and y <= cy <= y+h for x, y, w, h in bounds)
        if line.get('badge_read') or not chart_glyph or not covered:
            result.append(line)
    return result
