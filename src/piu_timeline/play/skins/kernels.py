"""Separable source-grid interpolation with an explicit finite source stencil."""
import math

import numpy as np

KERNELS={'area':{},'bicubic':{'b':0,'c':.6}}


def bicubic_weights(length,scale,phase):
    # FFmpeg swscale's documented default is Mitchell-Netravali B=0, C=.6.
    # Downscaling widens the source stencil before row normalization.
    rate=min(1.,scale);pad=math.ceil(2/rate)+1
    centers=(np.arange(math.ceil(length*scale+phase-1e-9))+.5-phase)/scale-.5
    distance=np.abs(centers[:,None]-np.arange(-pad,length+pad)[None,:])*rate
    d=distance;b,c=KERNELS['bicubic']['b'],KERNELS['bicubic']['c']
    inner=((12-9*b-6*c)*d**3+(-18+12*b+6*c)*d**2+6-2*b)/6
    outer=((-b-6*c)*d**3+(6*b+30*c)*d**2+(-12*b-48*c)*d+8*b+24*c)/6
    values=np.where(d<1,inner,np.where(d<2,outer,0.))
    values/=values.sum(axis=1,keepdims=True)
    return values,pad
