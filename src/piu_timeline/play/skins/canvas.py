"""Search only compared output pixels after the full source-grid resampling."""
import numpy as np


def comparison_canvas(model):
    rows,cols=np.nonzero(model['support'])
    left,top,right,bottom=int(cols.min()),int(rows.min()),int(cols.max())+1,int(rows.max())+1
    origin=model.get('sampling_origin_pixels',[0,0])
    result={**model,'sampling_origin_pixels':[origin[0]+left,origin[1]+top],
            'anchor':[model['anchor'][0]-left,model['anchor'][1]-top]}
    for name in ('rgb','mask','support','cap_support'):
        result[name]=model[name][top:bottom,left:right]
    result['regions']=[]
    for region in model['regions']:
        if region['mask'].any():
            a,b,c,d=region['box'];box=[a-left,b-top,c-left,d-top]
        else:box=[0,0,1,1]
        result['regions'].append({**region,'box':box})
    return result
