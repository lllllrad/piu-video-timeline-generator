"""Reuse independent cap/body acquisition only after exact reference validation."""
from hashlib import sha256
import json

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import FORMAT


def group(template):
    # Cap roles compete with one another; body minima are resolved separately.
    return 'body'if template['role']=='hold_body'else'caps'


def signatures(bank):
    result={'caps':[],'body':[]}
    for t in bank['templates']:
        value={k:t[k]for k in ('id','role','lane_kind','anchor_pixels','tap_clearance')}
        value['regions']=[{'name':r['name'],'box':r['box'],'maximum_error':r.get('maximum_error',.015)}for r in t['regions']]
        h=sha256(json.dumps(value,sort_keys=True).encode())
        # Unsupported RGB can affect area resampling at noninteger scales.
        h.update(t['rgb'].tobytes());h.update(t['mask'].tobytes())
        result[group(t)].append(h.hexdigest())
    return result


def reusable_groups(data,bank):
    saved=data.get('skin_detector',{})
    if saved.get('contract',{}).get('detector')!=FORMAT:return set()
    try:old=load_bank(saved['bank_path'])
    except (OSError,ValueError,KeyError):return set()
    if (old['contract']!=saved['contract']['bank'] or old['skin']!=bank['skin']
            or old['spacing_pixels']!=bank['spacing_pixels']):return set()
    a,b=signatures(old),signatures(bank)
    return {key for key in a if a[key]==b[key]}


def merge_observations(native,detected,reused):
    old=native.get('skin_observations',[])
    kept=[o for o in old if group(o)in reused]
    # Tracking consumes caps only. Body/cap ties carry no cross-role ownership.
    return sorted([*kept,*detected],key=lambda o:(o['lane'],o['y'],o['role']=='hold_body'))
