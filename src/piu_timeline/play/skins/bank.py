"""Source-independent RGB note-skin references with explicit image anchors."""
from hashlib import sha256
import json
from pathlib import Path

import cv2
import numpy as np

ROLES = ('tap', 'hold_start', 'hold_body', 'hold_end')
FORMAT = {'schema': 1, 'revision': 2, 'measurement': 'masked_rgb_regions'}
COMPARISON_FORMAT = {'schema':1,'method':'source_pixel_box_union'}


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
        evidence=entry.get('source_evidence',{})
        if not isinstance(evidence,dict):raise ValueError('Skin source evidence must be an object')
        if 'lane'in evidence:
            lane=evidence['lane']
            if type(lane)is not int or not 0<=lane<10 or lane%5!=entry['lane_kind']:
                raise ValueError('Skin lane kind disagrees with its recording source lane')
        image_path = (path.parent / entry['image']).resolve()
        if not image_path.is_relative_to(path.parent):
            raise ValueError('Skin images must stay within their bank directory')
        image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim != 3 or image.shape[2] != 4:
            raise ValueError('Skin references require RGBA PNG pixels and an explicit support mask')
        rgb, mask = image[:, :, :3][:, :, ::-1].copy(), image[:, :, 3] > 0
        height, width = mask.shape
        for box in entry.get('sampling_context',[]):
            if (not isinstance(box,list)or len(box)!=4 or not all(type(v)is int for v in box)
                    or not 0<=box[0]<box[2]<=width or not 0<=box[1]<box[3]<=height
                    or not mask[box[1]:box[3],box[0]:box[2]].all()):
                raise ValueError('Sampling context needs declared source pixels inside the reference image')
        anchor = entry.get('anchor_pixels', [])
        if (len(anchor) != 2 or not all(finite_number(x) for x in anchor)
                or not 0 <= anchor[0] < width or not 0 <= anchor[1] < height):
            raise ValueError('Skin template anchor must lie inside its image')
        if 'native_center_pixels'in entry:
            center=entry['native_center_pixels']
            if (not isinstance(center,list)or len(center)!=2 or not all(finite_number(v)for v in center)
                    or not 0<=center[0]<width or not 0<=center[1]<height or entry['role']=='hold_body'):
                raise ValueError('Native cap center must lie inside a cap reference image')
        if 'lane_centers_x'in evidence:
            centers=evidence['lane_centers_x'];dimensions=evidence.get('reference_dimensions',[])
            crop=evidence.get('source_crop',[])
            if (not isinstance(centers,list)or len(centers)not in(5,10)
                    or any(not finite_number(x)or not 0<x<1 for x in centers)
                    or any(a>=b for a,b in zip(centers,centers[1:]))
                    or len(dimensions)!=2 or any(type(v)is not int or v<=0 for v in dimensions)
                    or len(crop)!=4 or any(type(v)is not int for v in crop)
                    or not 0<=crop[0]<crop[2]<=dimensions[0]or not 0<=crop[1]<crop[3]<=dimensions[1]
                    or (crop[2]-crop[0],crop[3]-crop[1])!=(width,height)or 'lane'not in evidence):
                raise ValueError('Source lane geometry needs its original crop, dimensions and ordered lane centers')
            x=(crop[0]+anchor[0])/dimensions[0]
            distances=[abs(c-x)for c in centers];nearest=min(distances)
            choices=[i for i,distance in enumerate(distances)if abs(distance-nearest)<1e-9]
            if choices!=[evidence['lane']]:
                raise ValueError('Declared source lane disagrees with the reference crop position')
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
            if 'comparison_boxes'in region:
                boxes=region['comparison_boxes'];selected=np.zeros((y1-y0,x1-x0),dtype=bool)
                if not isinstance(boxes,list)or not boxes:raise ValueError('Comparison boxes must be a nonempty list')
                for box in boxes:
                    if (not isinstance(box,list)or len(box)!=4 or any(type(v)is not int for v in box)
                            or not x0<=box[0]<box[2]<=x1 or not y0<=box[1]<box[3]<=y1):
                        raise ValueError('Comparison box must stay inside its region')
                    a,b,c,d=box;selected[b-y0:d-y0,a-x0:c-x0]=True
                if np.count_nonzero(selected&mask[y0:y1,x0:x1])<8:
                    raise ValueError('Comparison boxes need eight supported source pixels')
        features=entry.get('cap_features',[])
        if (not isinstance(features,list)or any(not isinstance(v,str)for v in features)
                or len(set(features))!=len(features)or any(v not in names or v in ('cap','connection','body','clear_above','clear_below')for v in features)
                or features and entry['role']=='hold_body'):
            raise ValueError('Cap features must name distinct additional cap image regions')
        if features:
            cap=next(r['box']for r in regions if r['name']=='cap')
            for region in regions:
                if region['name']in features:
                    a,b,c,d=region['box']
                    if not cap[0]<=a<c<=cap[2]or not cap[1]<=b<d<=cap[3]:
                        raise ValueError('Cap feature must stay inside the cap region')
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
    bank={'skin': document['skin'], 'spacing_pixels': spacing, 'templates': templates,
          'contract': {'format': FORMAT, 'sha256': fingerprint.hexdigest(), 'skin': document['skin']}}
    if any('comparison_boxes'in r for t in templates for r in t['regions']):
        bank['contract']['comparison_geometry']=COMPARISON_FORMAT
    if any(t.get('cap_features')for t in templates):
        bank['contract']['cap_features']={'schema':1,'method':'independently_required_cap_regions'}
    from piu_timeline.play.skins.anchors import registered_anchors
    bank['anchor_registrations']=registered_anchors(bank)
    return bank
