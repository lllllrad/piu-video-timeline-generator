"""Exact visible-mask SSD maps with foreground weights shared across references."""
from collections import OrderedDict

import cv2
import numpy as np


class VisibleSearch:
    def __init__(self,image,foreground):
        self.cache=OrderedDict()
        self.visible=(~foreground).astype('float32')
        self.image=image*self.visible[:,:,None]
        self.squared=np.square(image).sum(axis=2)*self.visible

    def error(self,template,bounds):
        """Four correlations replace per-patch RGB/mask enumeration.

        sum(V*(I-R)^2) = sum(V*I^2) - 2*sum(V*I*R) + sum(V*R^2).
        V is observed visibility; none of the hidden reference RGB is evidence.
        Exact per-position masks still verify every proposed observation.
        """
        cap=next(r for r in template['regions']if r['name']=='cap')
        a,b,c,d=cap['box'];left,top,right,bottom=bounds;h,w=template['mask'].shape
        identity=(cap.get('_identity',id(cap)),left+a,top+b,right-w+c,bottom-h+d)
        if identity in self.cache:
            self.cache.move_to_end(identity);return self.cache[identity]
        area=(slice(top+b,bottom-h+d),slice(left+a,right-w+c))
        mask=cap['mask'].astype('float32');reference=template['rgb'][b:d,a:c]*mask[:,:,None]
        correlate=lambda image,pattern:cv2.matchTemplate(np.ascontiguousarray(image),np.ascontiguousarray(pattern),cv2.TM_CCORR)
        count=np.rint(correlate(self.visible[area],mask)).clip(0,float(mask.sum()))
        total=(correlate(self.squared[area],mask)-2*correlate(self.image[area],reference)
               +correlate(self.visible[area],np.square(reference).sum(axis=2)))
        result=np.maximum(total,0)/(3*np.maximum(count,1)),count
        self.cache[identity]=result
        if len(self.cache)>256:self.cache.popitem(last=False)
        return result
