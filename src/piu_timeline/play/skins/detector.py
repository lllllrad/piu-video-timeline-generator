"""Locate image patterns directly, without generating contour candidates first."""
import cv2
import numpy as np

from piu_timeline.play.screen_regions import occluders_at_bounds

FORMAT = {'schema': 1, 'revision': 1, 'method': 'lane_masked_rgb_regions',
          'horizontal_search_spacing': .12, 'same_anchor_spacing': .25}


class SkinDetector:
    def __init__(self, bank, layout, width, height):
        self.bank, self.layout, self.width, self.height = bank, layout, width, height
        self.spacing = float(np.median(np.diff([lane['x'] * width for lane in layout['lanes']])))
        self.templates = []
        scale = self.spacing / bank['spacing_pixels']
        for original in bank['templates']:
            h, w = original['mask'].shape
            size = max(2, round(w * scale)), max(2, round(h * scale))
            sx, sy = size[0] / w, size[1] / h
            rgb = cv2.resize(original['rgb'], size, interpolation=cv2.INTER_AREA).astype('float32') / 255
            mask = cv2.resize(original['mask'].astype('uint8'), size, interpolation=cv2.INTER_NEAREST)
            regions = []
            for region in original['regions']:
                x0, y0, x1, y1 = region['box']
                box = round(x0 * sx), round(y0 * sy), round(x1 * sx), round(y1 * sy)
                if box[0] >= box[2] or box[1] >= box[3] or not mask[box[1]:box[3], box[0]:box[2]].any():
                    raise ValueError('Skin image region vanishes at the analysis scale')
                regions.append({**region, 'box': box})
            self.templates.append({**original, 'rgb': rgb, 'mask': mask,
                                   'anchor': [original['anchor_pixels'][0] * sx, original['anchor_pixels'][1] * sy],
                                   'regions': regions})

    def detect(self, rgb):
        if rgb.shape != (self.height, self.width, 3):
            raise ValueError('Skin detector image differs from its geometry')
        image = rgb.astype('float32') / 255
        candidates = []
        for lane, column in enumerate(self.layout['lanes']):
            center = column['x'] * self.width
            for template in self.templates:
                if template['lane_kind'] != lane % 5:
                    continue
                h, w = template['mask'].shape
                ax, ay = template['anchor']
                radius = max(1, round(FORMAT['horizontal_search_spacing'] * self.spacing))
                left, right = max(0, round(center - ax) - radius), min(self.width, round(center - ax) + w + radius)
                top = max(0, int(self.layout['receptor_y'] * self.height + .55 * self.spacing - ay))
                bottom = min(self.height, round(self.layout.get('note_y_max', .95) * self.height))
                if right - left < w or bottom - top < h:
                    continue
                search = image[top:bottom, left:right]
                scores, errors = None, {}
                for region in template['regions']:
                    x0, y0, x1, y1 = region['box']
                    reference = template['rgb'][y0:y1, x0:x1]
                    mask = template['mask'][y0:y1, x0:x1]
                    # Every region yields the same candidate-origin matrix.
                    area = search[y0:search.shape[0] - h + y1, x0:search.shape[1] - w + x1]
                    error = cv2.matchTemplate(area, reference, cv2.TM_SQDIFF, mask=mask) / (3 * max(1, int(mask.sum())))
                    error = np.maximum(error, 0)
                    errors[region['name']] = error
                    normalized = error / region.get('maximum_error', .015)
                    scores = normalized if scores is None else np.maximum(scores, normalized)
                allowed = np.isfinite(scores) & (scores <= 1)
                # Keep local image minima; the contour detector is never called.
                minima = cv2.erode(scores.astype('float32'), np.ones((3, 3), dtype='uint8'))
                rows, cols = np.nonzero(allowed & (scores <= minima + 1e-7))
                for row, col in zip(rows, cols, strict=True):
                    x, y = left + col + ax, top + row + ay
                    bounds = [left + int(col), top + int(row), left + int(col) + w, top + int(row) + h]
                    if occluders_at_bounds(self.layout, bounds, self.width, self.height):
                        continue
                    candidates.append({'lane': lane, 'x': x / self.width, 'y': y / self.height,
                                       'role': template['role'], 'template': template['id'],
                                       'quality': float(1 - scores[row, col]),
                                       'region_errors': {name: float(values[row, col]) for name, values in errors.items()},
                                       'bounds_pixels': bounds, 'method': 'skin_image', 'skin': self.bank['skin']})
        return self.resolve(candidates)

    def resolve(self, candidates):
        retained = []
        for candidate in sorted(candidates, key=lambda c: c['quality'], reverse=True):
            peers = [r for r in retained if r['lane'] == candidate['lane']
                     and abs(r['y'] - candidate['y']) * self.height < FORMAT['same_anchor_spacing'] * self.spacing
                     and (r['role'] == 'hold_body') == (candidate['role'] == 'hold_body')]
            if not peers:
                retained.append({**candidate, 'alternatives': []})
                continue
            current = peers[0]
            proof = {k: candidate[k] for k in ('role', 'template', 'quality', 'region_errors')}
            current['alternatives'].append(proof)
            endpoints = {r['role'] for r in [current, candidate]} & {'hold_start', 'hold_end'}
            if len(endpoints) > 1:
                current.update(role='unknown', reason='competing_hold_endpoint_images')
            elif endpoints and current['role'] == 'tap':
                # A complete endpoint image includes its own cap AND connection.
                # A cap-only tap match cannot erase that additional evidence.
                alternatives = [{k: current[k] for k in ('role', 'template', 'quality', 'region_errors')},
                                *[r for r in current['alternatives'] if r is not proof]]
                current.update(candidate, alternatives=alternatives)
        return sorted(retained, key=lambda r: (r['lane'], r['y']))
