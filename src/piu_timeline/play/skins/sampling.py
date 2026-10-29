"""Resample references on the source grid without resetting their pixel phase."""
from fractions import Fraction
from itertools import product
import math

import numpy as np
from piu_timeline.play.skins.kernels import bicubic_weights,KERNELS

FORMAT={'schema':1,'revision':2,'method':'supported_source_grid','phase_grid':4,'exact_denominator_limit':8,
        'kernels':KERNELS}


def key(record):
    phase=record.get('sampling_phase_pixels')
    name=record.get('template',record.get('id'))
    if record.get('sampling_kernel','area')!='area':return(name,record['sampling_kernel'],*(phase or [0,0]))
    return (name,*phase)if phase is not None else name


def weights(length,scale,phase):
    edge=phase+np.arange(length+1)*scale
    output=np.arange(math.ceil(edge[-1]-1e-9))[:,None]
    return np.maximum(0,np.minimum(output+1,edge[None,1:])-np.maximum(output,edge[None,:-1]))


def phases(scale):
    exact=Fraction(float(scale)).limit_denominator(FORMAT['exact_denominator_limit'])
    count=exact.denominator if abs(float(exact)-scale)<1e-9 else FORMAT['phase_grid']
    return [i/count for i in range(count)]


def models(original,scale):
    kernels=['area']if abs(scale-1)<1e-9 else ['area','bicubic']
    for kernel in kernels:yield from kernel_models(original,scale,kernel)


def kernel_models(original,scale,kernel):
    h,w=original['mask'].shape
    options=phases(scale)
    for px,py in product(options,repeat=2):
        if kernel=='area':wx,wy,xpad,ypad=weights(w,scale,px),weights(h,scale,py),0,0
        else:
            wx,xpad=bicubic_weights(w,scale,px);wy,ypad=bicubic_weights(h,scale,py)
        image=np.pad(original['rgb'],((ypad,ypad),(xpad,xpad),(0,0)))
        rgb=np.stack([wy@image[:,:,c]@wx.T for c in range(3)],axis=-1).clip(0,255).astype('float32')/255
        support=np.zeros(rgb.shape[:2],dtype=bool);cap_support=np.zeros_like(support);regions=[]
        source=np.pad(original['mask'].astype(float),((ypad,ypad),(xpad,xpad)))
        if kernel=='area':known=wy@source@wx.T>=1-1e-8
        else:
            # Negative coefficients cannot cancel unknown source pixels into
            # apparent support. Every nonzero kernel tap must be declared.
            known=(np.abs(wy)>1e-8).astype(float)@(1-source)@(np.abs(wx)>1e-8).astype(float).T==0
        cx=(np.arange(rgb.shape[1])+.5-px)/scale;cy=(np.arange(rgb.shape[0])+.5-py)/scale
        for region in original['regions']:
            a,b,c,d=region['box']
            # Regions select output locations. Their interpolation stencil may
            # include an adjacent declared region, never unsupported padding.
            valid=known&((cy>=b)&(cy<d))[:,None]&((cx>=a)&(cx<c))[None,:]
            if 'comparison_boxes'in region:
                selected=np.zeros_like(known)
                for x0,y0,x1,y1 in region['comparison_boxes']:
                    selected|=((cy>=y0)&(cy<y1))[:,None]&((cx>=x0)&(cx<x1))[None,:]
                valid&=selected
            ys,xs=np.nonzero(valid)
            if not len(xs):
                regions.append({**region,'box':[0,0,1,1],'mask':np.zeros((1,1),dtype='uint8')});continue
            box=[int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1]
            a,b,c,d=box
            regions.append({**region,'box':box,'mask':valid[b:d,a:c].astype('uint8')})
            support|=valid
            if region['name']=='cap':cap_support|=valid
        if not (cap_support.any()if any(r['name']=='cap'for r in original['regions'])else support.any()):continue
        phase={}if len(options)==1 else {'sampling_phase_pixels':[px,py]}
        yield {**original,**phase,**({'sampling_kernel':kernel}if kernel!='area'else{}),'rgb':rgb,'mask':support.astype('uint8'),
               'anchor':[px+scale*original['anchor_pixels'][0],py+scale*original['anchor_pixels'][1]],
               'reference_scale_y':scale,'regions':regions,'support':support,'cap_support':cap_support}
