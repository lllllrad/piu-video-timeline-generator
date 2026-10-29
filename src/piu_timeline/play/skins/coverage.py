"""Vertical support of compared reference pixels, excluding image padding."""
import numpy as np

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.sampling import key,models


def reference_rows(data, *, cap_only=False):
    bank=load_bank(data['skin_detector']['bank_path'])
    if bank['contract']!=data['skin_detector']['contract']['bank']:
        raise ValueError('Hold image references differ from the acquired observation bank')
    spacing=float(np.median(np.diff([lane['x']*data['analysis_width']for lane in data['layout']['lanes']])))
    result={}
    for template in (model for original in bank['templates']for model in models(original,spacing/bank['spacing_pixels'])):
        support=template['cap_support']if cap_only else template['support']
        rows=np.flatnonzero(support.any(axis=1))
        runs=[]
        for row in rows:
            row=int(row)
            if runs and runs[-1][1]==row:runs[-1][1]=row+1
            else:runs.append([row,row+1])
        result[key(template)]=runs
    return result


def image_spans(image,references,*,cap_only=False):
    """These are compared image rows, not a claim of solid foreground pixels."""
    patterns=[image]
    if cap_only and image.get('role')=='unknown'and image.get('classification_status')=='cap_only':
        patterns.extend(p for p in image.get('alternatives',[])
                        if p.get('role')=='unknown'and p.get('classification_status')=='cap_only')
    if image.get('role')in('hold_start','hold_body','hold_end'):
        patterns.extend(p for p in image.get('alternatives',[])
                        if p['role']==image['role'] and p.get('classification_status')=='full_pattern')
    return [(p['bounds_pixels'][1]+a-p.get('sampling_origin_pixels',[0,0])[1],
             p['bounds_pixels'][1]+b-p.get('sampling_origin_pixels',[0,0])[1])
            for p in patterns for a,b in references[key(p)]]
