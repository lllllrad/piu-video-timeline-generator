"""Vertical support of compared reference pixels, excluding image padding."""
import numpy as np

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector


def reference_rows(data):
    bank=load_bank(data['skin_detector']['bank_path'])
    if bank['contract']!=data['skin_detector']['contract']['bank']:
        raise ValueError('Hold image references differ from the acquired observation bank')
    detector=SkinDetector(bank,data['layout'],data['analysis_width'],data['analysis_height'])
    result={}
    for template in detector.templates:
        rows=np.flatnonzero(template['support'].any(axis=1))
        runs=[]
        for row in rows:
            row=int(row)
            if runs and runs[-1][1]==row:runs[-1][1]=row+1
            else:runs.append([row,row+1])
        result[template['id']]=runs
    return result


def image_spans(image,references):
    """These are compared image rows, not a claim of solid foreground pixels."""
    top=image['bounds_pixels'][1]
    return [(top+a,top+b)for a,b in references[image['template']]]
