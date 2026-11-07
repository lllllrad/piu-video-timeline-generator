"""Vertical support of compared reference pixels, excluding image padding."""
import numpy as np

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.sampling import key,models,reference_scale


def reference_models(data):
    bank=load_bank(data['skin_detector']['bank_path'])
    if bank['contract']!=data['skin_detector']['contract']['bank']:
        raise ValueError('Hold image references differ from the acquired observation bank')
    scale=reference_scale(bank,data['layout'],data['analysis_width'],data['analysis_height'])
    return (model for original in bank['templates']for model in models(original,scale))


def negative_regions(data):
    return {key(t):[r for r in t['regions']if r['name']in('clear_above','clear_below')]
            for t in reference_models(data)}


class ReferenceRows(dict):
    def __init__(self,selection):
        super().__init__();self.selection=selection


def reference_rows(data, *, cap_only=False, body_only=False):
    if cap_only and body_only:raise ValueError('Select cap or connector support, not both')
    result=ReferenceRows('cap'if cap_only else'body'if body_only else'all')
    for template in reference_models(data):
        support=template['cap_support']if cap_only else template['support']
        if body_only:
            support=np.zeros_like(support)
            for region in template['regions']:
                if region['name']not in('connection','body'):continue
                a,b,c,d=region['box'];support[b:d,a:c]|=region['mask'].astype(bool)
        rows=np.flatnonzero(support.any(axis=1))
        runs=[]
        for row in rows:
            row=int(row)
            if runs and runs[-1][1]==row:runs[-1][1]=row+1
            else:runs.append([row,row+1])
        result[key(template)]=runs
    return result


def image_spans(image,references,*,cap_only=False,full_only=False):
    """These are compared image rows, not a claim of solid foreground pixels."""
    patterns=[image]
    if cap_only and image.get('role')=='unknown'and image.get('classification_status')=='cap_only':
        patterns.extend(p for p in image.get('alternatives',[])
                        if p.get('role')=='unknown'and p.get('classification_status')=='cap_only')
    if image.get('role')in('hold_start','hold_body','hold_end'):
        patterns.extend(p for p in image.get('alternatives',[])
                        if p['role']==image['role'] and p.get('classification_status')=='full_pattern')
    if cap_only and 'visible_cap_runs'in image:
        rows=sorted({image['bounds_pixels'][1]+row for row,_,_ in image['visible_cap_runs']})
        return [(row,row+1)for row in rows]
    combined=[]
    for pattern in patterns:
        shared=pattern.get('shared_role')
        if shared is None:continue
        selection='cap'if cap_only else getattr(references,'selection','all')
        if selection!='body':combined.extend(tuple(r)for r in shared['cap_rows_pixels'])
        if selection!='cap':combined.extend(tuple(r)for r in shared['context']['connection_rows_pixels'])
    ordinary=[]
    selection='cap'if cap_only else getattr(references,'selection','all')
    for p in patterns:
        if 'shared_role'in p:continue
        if full_only and p.get('classification_status','full_pattern')!='full_pattern':continue
        if 'visible_connection_runs'not in p:
            ordinary.append(p);continue
        top=p['bounds_pixels'][1]
        if selection!='body':combined.extend((top+y,top+y+1)for y,_,_ in p['visible_cap_runs'])
        if selection!='cap':combined.extend((top+y,top+y+1)for y,_,_ in p['visible_connection_runs'])
    return combined+[(p['bounds_pixels'][1]+a-p.get('sampling_origin_pixels',[0,0])[1],
             p['bounds_pixels'][1]+b-p.get('sampling_origin_pixels',[0,0])[1])
            for p in ordinary for a,b in references[key(p)]]
