"""Per-observation coordinate views, measured before assigning trajectory identity."""
import math
import numpy as np

from piu_timeline.play.skins.anchors import cap_reference
from piu_timeline.play.skins.coordinates import registered_comparison,validate_origin
from piu_timeline.play.skins.sampling import reference_scale
from piu_timeline.play.skins.subfeatures import shared_cap_pixels
from piu_timeline.derived import CONTRACTS


class FrameCenters:
    def __init__(self,detector):
        self.bank=detector.bank;self.layout=detector.layout
        self.width,self.height=detector.width,detector.height
        self.templates={t['id']:t for t in self.bank['templates']}
        self.comparisons=detector.by_sampling
        self.scale=reference_scale(self.bank,self.layout,self.width,self.height)
        self.references={name:cap_reference(self.bank,t)for name,t in self.templates.items()
                         if any(r['name']=='cap'for r in t['regions'])}

    def position(self,image):
        lane=image['lane'];name=image['template'];height=self.height
        if image.get('skin')!=self.bank['skin']or self.templates[name]['lane_kind']!=lane%5:
            raise ValueError('Tracking image belongs to another skin or lane')
        patterns=[image,*image.get('alternatives',[])]
        for candidate in patterns:
            template=self.templates[candidate['template']]
            if candidate.get('lane',lane)!=lane or template['lane_kind']!=lane%5:
                raise ValueError('Tracking comparison belongs to another lane')
            validate_origin(candidate,template,self.width,height,self.scale)
        cap=next(r for r in self.templates[name]['regions']if r['name']=='cap')
        error=image.get('region_errors',{}).get('cap')
        if (not isinstance(error,(int,float))or not math.isfinite(error)or error<0
                or np.float32(error)/cap.get('maximum_error',.015)>1):
            raise ValueError('Tracking image lacks a positive cap comparison')
        raw=image['y']*height
        measured,conflict=registered_comparison(image,self.bank,self.templates,lane,raw,height,self.scale,self.comparisons)
        equivalent=[p['y']*height for p in patterns if self.references.get(p['template'])==self.references[name]]
        anchor={'yPixels':raw,'uncertaintyPixels':.5+max(abs(y-raw)for y in equivalent),
                'basis':{'kind':'image_reference_anchor','reference':{'kind':'sha256','value':self.references[name]}}}
        positions={self.references[name]:[p['y']*height for p in patterns if self.references.get(p['template'])==self.references[name]]}
        for candidate in patterns:
            identity=self.references[candidate['template']]
            if identity==self.references[name]:continue
            region=next(r for r in self.templates[candidate['template']]['regions']if r['name']=='cap')
            error=candidate.get('region_errors',{}).get('cap')
            if (not isinstance(error,(int,float))or not math.isfinite(error)or error<0
                    or np.float32(error)/region.get('maximum_error',.015)>1):continue
            if shared_cap_pixels(image,candidate,self.comparisons,CONTRACTS['image_coordinates']['minimum_same_cap_support_fraction']):
                positions.setdefault(identity,[]).append(candidate['y']*height)
        anchors=[{'yPixels':(min(rows)+max(rows))/2,'uncertaintyPixels':.5+(max(rows)-min(rows))/2,
                  'basis':{'kind':'image_reference_anchor','reference':{'kind':'sha256','value':identity}}}
                 for identity,rows in positions.items()]
        center=None
        if not conflict and 'native_cap_coordinate_uncertainty_pixels'in measured:
            center={'yPixels':measured['native_y_pixels'],
                    'uncertaintyPixels':measured['native_cap_coordinate_uncertainty_pixels'],
                    'basis':{'kind':'native_cap_center'}}
        return {'anchor':anchor,'anchors':anchors,'center':center}
