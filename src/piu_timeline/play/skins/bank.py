"""Source-independent RGB note-skin references with explicit image anchors."""
from hashlib import sha256
import json
from pathlib import Path

import cv2
import numpy as np

ROLES = ('tap', 'hold_start', 'hold_body', 'hold_end')
FORMAT = {'schema': 1, 'revision': 2, 'measurement': 'masked_rgb_regions'}


def finite_number(value):
    return type(value) in (int, float) and np.isfinite(value)


def load_bank(path):
    """Load only local references; image bytes participate in cache identity."""
    path = Path(path).resolve()
    document = json.loads(path.read_text())
    if document.get('schema') != 1 or not isinstance(document.get('skin'), str) or not document['skin'].strip():
        raise ValueError('Skin bank requires schema 1 and a skin identity')
    spacing = document.get('spacing_pixels')
    if not finite_number(spacing) or spacing <= 0:
        raise ValueError('Skin bank needs measured reference lane spacing')
    templates, fingerprint, identifiers = [], sha256(path.read_bytes()), set()
    for entry in document.get('templates', []):
        identifier = entry.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError('Skin template identities must be nonempty and unique')
        identifiers.add(identifier)
        if entry.get('role') not in ROLES or type(entry.get('lane_kind')) is not int or not 0 <= entry['lane_kind'] < 5:
            raise ValueError('Skin template requires a note role and a lane kind from 0 to 4')
        image_path = (path.parent / entry['image']).resolve()
        if not image_path.is_relative_to(path.parent):
            raise ValueError('Skin images must stay within their bank directory')
        image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim != 3 or image.shape[2] != 4:
            raise ValueError('Skin references require RGBA PNG pixels and an explicit support mask')
        rgb, mask = image[:, :, :3][:, :, ::-1].copy(), image[:, :, 3] > 0
        height, width = mask.shape
        anchor = entry.get('anchor_pixels', [])
        if (len(anchor) != 2 or not all(finite_number(x) for x in anchor)
                or not 0 <= anchor[0] < width or not 0 <= anchor[1] < height):
            raise ValueError('Skin template anchor must lie inside its image')
        regions = entry.get('regions', [])
        names = {r.get('name') for r in regions}
        required = {'cap', 'connection'} if entry['role'] in ('hold_start', 'hold_end') else {'body'} if entry['role'] == 'hold_body' else {'cap'}
        if not required <= names or len(names) != len(regions):
            raise ValueError('Hold caps require separate cap and connection image regions')
        for region in regions:
            box, error = region.get('box', []), region.get('maximum_error', .015)
            if (len(box) != 4 or not all(type(x) is int for x in box)
                    or not 0 <= box[0] < box[2] <= width or not 0 <= box[1] < box[3] <= height
                    or not finite_number(error) or not 0 < error <= .03):
                raise ValueError('Skin region requires valid bounds and a bounded RGB error')
            x0, y0, x1, y1 = box
            if mask[y0:y1, x0:x1].sum() < 8:
                raise ValueError('Each skin region needs at least eight supported image pixels')
        if entry['role'] in ('hold_start', 'hold_end'):
            connection = next(r['box'] for r in regions if r['name'] == 'connection')
            if ((entry['role'] == 'hold_start' and connection[1] <= anchor[1])
                    or (entry['role'] == 'hold_end' and connection[3] > anchor[1])):
                raise ValueError('Hold start connection must be below its anchor; hold end connection must be above')
        clearance={'clear_above','clear_below'} & names
        if entry['role']=='tap' and clearance:
            if clearance!={'clear_above','clear_below'}:
                raise ValueError('A tap needs both upper and lower clearance regions')
            boxes={r['name']:r['box']for r in regions}
            if boxes['clear_above'][3]>boxes['cap'][1] or boxes['clear_below'][1]<boxes['cap'][3]:
                raise ValueError('Tap clearance regions must be outside the cap image')
        fingerprint.update(image_path.read_bytes())
        templates.append({**entry, 'rgb': rgb, 'mask': mask, 'regions': regions,
                          'tap_clearance':entry['role']=='tap' and bool(clearance)})
    if not templates:
        raise ValueError('Skin bank contains no image templates')
    return {'skin': document['skin'], 'spacing_pixels': spacing, 'templates': templates,
            'contract': {'format': FORMAT, 'sha256': fingerprint.hexdigest(), 'skin': document['skin']}}
