"""Area-resample reference cells without resetting their source sampling phase."""
from fractions import Fraction
from itertools import product
import math

import numpy as np

FORMAT={'schema':1,'method':'supported_source_cell_area','phase_grid':4,'exact_denominator_limit':8}


def key(record):
    phase=record.get('sampling_phase_pixels')
    return (record.get('template',record.get('id')),*phase)if phase is not None else record.get('template',record.get('id'))


def weights(length,scale,phase):
    edge=phase+np.arange(length+1)*scale
    output=np.arange(math.ceil(edge[-1]-1e-9))[:,None]
    return np.maximum(0,np.minimum(output+1,edge[None,1:])-np.maximum(output,edge[None,:-1]))


def phases(scale):
    exact=Fraction(float(scale)).limit_denominator(FORMAT['exact_denominator_limit'])
    count=exact.denominator if abs(float(exact)-scale)<1e-9 else FORMAT['phase_grid']
    return [i/count for i in range(count)]


def models(original,scale):
    h,w=original['mask'].shape
    for px,py in product(phases(scale),repeat=2):
        wx,wy=weights(w,scale,px),weights(h,scale,py)
        rgb=np.stack([wy@original['rgb'][:,:,c]@wx.T for c in range(3)],axis=-1).astype('float32')/255
        support=np.zeros(rgb.shape[:2],dtype=bool);cap_support=np.zeros_like(support);regions=[]
        for region in original['regions']:
            a,b,c,d=region['box'];source=np.zeros((h,w),dtype=float)
            source[b:d,a:c]=original['mask'][b:d,a:c]
            # Every contributing source cell must be positively supported in
            # this region. Padding and neighboring regions cannot fill it.
            valid=wy@source@wx.T>=1-1e-8
            ys,xs=np.nonzero(valid)
            if not len(xs):break
            box=[int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1]
            a,b,c,d=box
            regions.append({**region,'box':box,'mask':valid[b:d,a:c].astype('uint8')})
            support|=valid
            if region['name']=='cap':cap_support|=valid
        else:
            phase={}if len(phases(scale))==1 else {'sampling_phase_pixels':[px,py]}
            yield {**original,**phase,'rgb':rgb,'mask':support.astype('uint8'),
                   'anchor':[px+scale*original['anchor_pixels'][0],py+scale*original['anchor_pixels'][1]],
                   'reference_scale_y':scale,'regions':regions,'support':support,'cap_support':cap_support}
