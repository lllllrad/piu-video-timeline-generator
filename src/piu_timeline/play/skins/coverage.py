"""Vertical support of compared reference pixels, excluding image padding."""
import numpy as np

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.sampling import key


def reference_rows(data, *, cap_only=False):
    bank=load_bank(data['skin_detector']['bank_path'])
    if bank['contract']!=data['skin_detector']['contract']['bank']:
        raise ValueError('Hold image references differ from the acquired observation bank')
    detector=SkinDetector(bank,data['layout'],data['analysis_width'],data['analysis_height'])
    result={}
    for template in detector.templates:
        support=template['cap_support']if cap_only else template['support']
        rows=np.flatnonzero(support.any(axis=1))
        runs=[]
        for row in rows:
            row=int(row)
            if runs and runs[-1][1]==row:runs[-1][1]=row+1
            else:runs.append([row,row+1])
        result[key(template)]=runs
    return result


def image_spans(image,references):
    """These are compared image rows, not a claim of solid foreground pixels."""
    patterns=[image]
    if image.get('role')in('hold_start','hold_body','hold_end'):
        patterns.extend(p for p in image.get('alternatives',[])
                        if p['role']==image['role'] and p.get('classification_status')=='full_pattern')
    return [(p['bounds_pixels'][1]+a,p['bounds_pixels'][1]+b)
            for p in patterns for a,b in references[key(p)]]
