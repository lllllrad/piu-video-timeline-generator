"""Resample references on the source grid without resetting their pixel phase."""
from fractions import Fraction
from itertools import product
import math

import numpy as np
from piu_timeline.play.skins.kernels import bicubic_weights,KERNELS

FORMAT={'schema':1,'revision':4,'method':'supported_source_grid','phase_grid':4,'exact_denominator_limit':8,
        'cap_proposal_stencil':'positive_cap_source_pixels_only','cap_boundary':'independent_context_comparison',
        'cap_foreground_fraction':'normalized_absolute_source_kernel_mass',
        'comparison_canvas':{'schema':1,'method':'compared_pixel_extent','origin':'resampled_reference_pixels'},
        'kernels':KERNELS}


def reference_scale(bank,layout,width,height):
    """Use an explicitly declared full-game grid before approximate lane spacing.

    A fixed HUD layout locates lanes; it does not measure reference-image size.
    Preserve the legacy spacing model for undeclared or nonuniform frame grids.
    """
    frame=bank.get('reference_frame')
    if frame:
        sx,sy=width/frame['width'],height/frame['height']
        if abs(sx-sy)<1e-9:return sx
    spacing=float(np.median(np.diff([lane['x']*width for lane in layout['lanes']])))
    return spacing/bank['spacing_pixels']


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
    cap_source=np.zeros((h,w),dtype=bool)
    for region in original['regions']:
        if region['name']not in {'cap',*original.get('cap_features',[])}:continue
        for a,b,c,d in region.get('comparison_boxes',[region['box']]):cap_source[b:d,a:c]|=original['mask'][b:d,a:c].astype(bool)
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
        cap_pixels=np.pad(cap_source.astype(float),((ypad,ypad),(xpad,xpad)))
        abs_x,abs_y=np.abs(wx),np.abs(wy)
        cap_fraction=(abs_y@cap_pixels@abs_x.T)/(abs_y.sum(axis=1)[:,None]*abs_x.sum(axis=1)[None,:])
        if kernel=='area':cap_known=wy@cap_pixels@wx.T>=1-1e-8
        else:cap_known=(np.abs(wy)>1e-8).astype(float)@(1-cap_pixels)@(np.abs(wx)>1e-8).astype(float).T==0
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
            if region['name']in {'cap',*original.get('cap_features',[])}:cap_support|=valid
        if not (cap_support.any()if any(r['name']=='cap'for r in original['regions'])else support.any()):continue
        phase={}if len(options)==1 else {'sampling_phase_pixels':[px,py]}
        core=cap_support&cap_known
        core_rows,core_cols=np.nonzero(core)
        core_region=None
        if len(core_rows):
            a,b,c,d=int(core_cols.min()),int(core_rows.min()),int(core_cols.max())+1,int(core_rows.max())+1
            cap=next(r for r in original['regions']if r['name']=='cap')
            core_region={**cap,'box':[a,b,c,d],'mask':core[b:d,a:c].astype('uint8')}
        yield {**original,**phase,**({'sampling_kernel':kernel}if kernel!='area'else{}),'rgb':rgb,'mask':support.astype('uint8'),
               'anchor':[px+scale*original['anchor_pixels'][0],py+scale*original['anchor_pixels'][1]],
               'reference_scale_y':scale,'regions':regions,'support':support,'cap_support':cap_support,
               'cap_core_support':core,'cap_core_region':core_region,'cap_foreground_fraction':cap_fraction}
