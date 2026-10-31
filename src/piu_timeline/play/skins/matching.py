"""Cap-first image comparisons with exact, bounded reuse inside one frame."""
from collections import OrderedDict
from hashlib import sha256

import cv2
import numpy as np


def prepare_regions(template):
    for region in template['regions']:
        x0,y0,x1,y1=region['box']
        reference=template['rgb'][y0:y1,x0:x1]
        region['_reference']=reference
        region['_pixels']=int(region['mask'].sum())
        digest=sha256(str(reference.shape).encode())
        digest.update(reference.tobytes());digest.update(region['mask'].tobytes())
        region['_identity']=digest.digest()


class RegionSearch:
    """No scores survive a frame boundary or skip competing image roles."""
    def __init__(self,image):
        self.image=image
        self.cache=OrderedDict()

    def error(self,template,region,bounds):
        left,top,right,bottom=bounds
        h,w=template['mask'].shape
        x0,y0,x1,y1=region['box']
        area=(left+x0,top+y0,right-w+x1,bottom-h+y1)
        identity=(region['_identity'],area)
        if identity in self.cache:
            self.cache.move_to_end(identity)
            return self.cache[identity]
        a,b,c,d=area
        value=(cv2.matchTemplate(self.image[b:d,a:c],region['_reference'],cv2.TM_SQDIFF,
                                mask=region['mask'])/(3*region['_pixels']) if region['_pixels']
               else np.full((bottom-top-h+1,right-left-w+1),np.inf,dtype='float32'))
        value=np.maximum(value,0)
        self.cache[identity]=value
        if len(self.cache)>256:self.cache.popitem(last=False)
        return value

    def evaluate(self,template,bounds):
        regions=template['regions']
        has_cap=any(r['name']=='cap'for r in regions)
        required={'cap',*template.get('cap_features',[])}if has_cap else {r['name']for r in regions}
        # A failed cap cannot become a candidate through a connector or background.
        primary=sorted((r for r in regions if r['name']in required),key=lambda r:r['name']!='cap')
        errors={};proposal=None
        for region in primary:
            error=self.error(template,region,bounds);errors[region['name']]=error
            normalized=error/region.get('maximum_error',.015)
            proposal=normalized if proposal is None else np.maximum(proposal,normalized)
            if not (np.isfinite(proposal)&(proposal<=1)).any():return None
        scores=proposal
        for region in regions:
            if region['name']in required:continue
            error=self.error(template,region,bounds);errors[region['name']]=error
            scores=np.maximum(scores,error/region.get('maximum_error',.015))
        return scores,proposal,errors
