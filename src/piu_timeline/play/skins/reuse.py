"""Reuse independent lane-kind cap/body acquisition after exact reference validation."""
from hashlib import sha256
import json

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import FORMAT


def group(template):
    # Roles compete within a lane; both player sides use the same lane kind.
    kind=template['lane_kind']if 'lane_kind'in template else template['lane']%5
    return f"{'body'if template['role']=='hold_body'else'caps'}/{kind}"


def signatures(bank):
    result={}
    for t in bank['templates']:
        value={k:t[k]for k in ('id','role','lane_kind','anchor_pixels','tap_clearance')}
        if t.get('cap_features'):value['cap_features']=t['cap_features']
        value['regions']=[{'name':r['name'],'box':r['box'],'maximum_error':r.get('maximum_error',.015),
                           **({'comparison_boxes':r['comparison_boxes']}if 'comparison_boxes'in r else{})}for r in t['regions']]
        h=sha256(json.dumps(value,sort_keys=True).encode())
        # Unsupported RGB can affect area resampling at noninteger scales.
        h.update(t['rgb'].tobytes());h.update(t['mask'].tobytes())
        result.setdefault(group(t),[]).append(h.hexdigest())
    return result


def reusable_groups(data,bank):
    saved=data.get('skin_detector',{})
    previous=saved.get('contract',{}).get('detector',{})
    if not isinstance(previous,dict):return set()
    # A body-only selection change does not alter cap comparison or localization.
    common=lambda contract:{k:v for k,v in contract.items()if k!='body_candidates'}
    if common(previous)!=common(FORMAT):return set()
    try:old=load_bank(saved['bank_path'])
    except (OSError,ValueError,KeyError):return set()
    if (old['contract']!=saved['contract']['bank'] or old['skin']!=bank['skin']
            or old['spacing_pixels']!=bank['spacing_pixels']
            or old.get('reference_frame')!=bank.get('reference_frame')):return set()
    a,b=signatures(old),signatures(bank)
    # Caps can occlude one another across lanes. A changed cap reference can
    # expose or hide a candidate from any other kind, so caps form one input set.
    cap_inputs=lambda signatures:{k:v for k,v in signatures.items()if k.startswith('caps/')}
    same_caps=cap_inputs(a)==cap_inputs(b)
    return {key for key in a.keys()&b.keys()if a[key]==b[key]
            and(same_caps if key.startswith('caps/')else previous==FORMAT)}


def merge_observations(native,detected,reused):
    old=native.get('skin_observations',[])
    kept=[o for o in old if group(o)in reused]
    # Tracking consumes caps only. Body/cap ties carry no cross-role ownership.
    return sorted([*kept,*detected],key=lambda o:(o['lane'],o['y'],o['role']=='hold_body'))
