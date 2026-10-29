"""Bind a reference's native vertical cap convention to its actual source pixels."""
from hashlib import sha256
import json
import math

from piu_timeline.derived import CONTRACTS

FORMAT = CONTRACTS['native_anchor']


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def cap_reference(bank,template):
    """Exact reference/anchor equality survives different context windows."""
    cap=next(r for r in template['regions']if r['name']=='cap')
    specification={'spacing_pixels':bank['spacing_pixels'],'lane_kind':template['lane_kind'],
                   'anchor':template['anchor_pixels'],'shape':template['rgb'].shape,
                   'cap_box':cap['box'],'cap_maximum_error':cap.get('maximum_error',.015)}
    if 'comparison_boxes'in cap:specification['comparison_boxes']=cap['comparison_boxes']
    if template.get('cap_features'):
        specification['cap_features']=[{**r,'maximum_error':r.get('maximum_error',.015)}
            for name in template['cap_features']for r in template['regions']if r['name']==name]
    fingerprint=sha256(json.dumps(specification,sort_keys=True).encode())
    # Full image bytes also bound resampling effects at the cap boundary.
    fingerprint.update(template['rgb'].tobytes());fingerprint.update(template['mask'].tobytes())
    return fingerprint.hexdigest()


def native_geometry(bank,template,sample,crop):
    """Only the measured source-frame center can establish this convention."""
    evidence=template.get('source_evidence',{})
    values=[sample.get(k)for k in ('time','source_pts_seconds','detected_y_pixels','offset_pixels')]
    if any(type(v)not in(int,float)or not math.isfinite(v)for v in values):
        raise ValueError('Anchor proof needs finite native measurements')
    if (abs(sample['time']-evidence.get('playback_seconds',float('inf')))>1e-6
            or abs(sample['source_pts_seconds']-evidence.get('source_pts_seconds',float('inf')))>1e-6):
        raise ValueError('Anchor proof differs from source frame timestamps')
    width,height=evidence.get('reference_dimensions',[0,0]);h,w=template['mask'].shape
    if (not isinstance(crop,list)or len(crop)!=4 or any(type(x)is not int for x in crop)
            or not 0<=crop[0]<crop[2]<=width or not 0<=crop[1]<crop[3]<=height
            or (crop[2]-crop[0],crop[3]-crop[1])!=(w,h)):
        raise ValueError('Anchor proof needs the original reference crop geometry')
    declared=evidence.get('source_crop',template.get('source_crop'))
    if crop!=declared:raise ValueError('Anchor proof source crop changed')
    if abs(sample['offset_pixels'])>FORMAT['maximum_offset_spacing']*bank['spacing_pixels']:
        raise ValueError('Anchor proof native offset exceeds the measurement limit')
    expected=sample['detected_y_pixels']+sample['offset_pixels']-crop[1]
    if abs(template['anchor_pixels'][1]-expected)>1e-6:
        raise ValueError('Reference anchor disagrees with the measured native center')
    if 'template'in sample:
        similarity,alternative=sample.get('similarity'),sample.get('alternative_similarity')
        if (any(type(v)not in(int,float)or not math.isfinite(v)for v in (similarity,alternative))
                or similarity<FORMAT['minimum_similarity']
                or similarity-alternative<FORMAT['alternative_margin']-1e-9):
            raise ValueError('Anchor proof lacks an independently qualified cap match')


def validate(bank,template,proof):
    if template['role']=='hold_body':raise ValueError('Body tiles cannot register a cap center')
    if proof.get('format')!=FORMAT:raise ValueError('Unsupported native anchor proof format')
    if proof.get('cap_reference_sha256')!=cap_reference(bank,template):
        raise ValueError('Native anchor proof belongs to different reference pixels or geometry')
    if proof.get('source_evidence_sha256')!=digest(template.get('source_evidence',{})):
        raise ValueError('Native anchor proof source identity changed')
    for key in ('source_artifact_sha256','source_frame_sha256'):
        value=proof.get(key)
        if not isinstance(value,str)or len(value)!=64 or any(c not in '0123456789abcdef'for c in value):
            raise ValueError('Native anchor proof needs source artifact and RGB frame identities')
    native_geometry(bank,template,proof['native_measurement'],proof['source_crop'])
    return {'coordinate_uncertainty_pixels':FORMAT['coordinate_uncertainty_pixels'],
            'cap_reference_sha256':proof['cap_reference_sha256']}


def certificate(bank,template,sample,crop,artifact_sha256,frame_sha256):
    proof={'format':FORMAT,'cap_reference_sha256':cap_reference(bank,template),
           'source_evidence_sha256':digest(template.get('source_evidence',{})),
           'source_artifact_sha256':artifact_sha256,'source_frame_sha256':frame_sha256,
           'source_crop':crop,'native_measurement':sample}
    validate(bank,template,proof)
    return proof


def registered_anchors(bank):
    return {t['id']:validate(bank,t,t['native_anchor_registration'])for t in bank['templates']
            if 'native_anchor_registration'in t}
