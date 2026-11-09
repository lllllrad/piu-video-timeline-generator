"""Per-observation coordinate views, measured before assigning trajectory identity."""
import math
import numpy as np

from piu_timeline.play.skins.anchors import cap_reference
from piu_timeline.play.skins.coordinates import comparison_input,validate_origin
from piu_timeline.play.skins.sampling import reference_scale


class FrameCenters:
    def __init__(self,detector):
        self.bank=detector.bank;self.layout=detector.layout
        self.width,self.height=detector.width,detector.height
        self.templates={t['id']:t for t in self.bank['templates']}
        self.comparisons=detector.by_sampling
        self.scale=reference_scale(self.bank,self.layout,self.width,self.height)
        self.references={name:cap_reference(self.bank,t)for name,t in self.templates.items()
                         if any(r['name']=='cap'for r in t['regions'])}
        self.cap_height_pixels=max((int(np.ptp(np.nonzero(t['cap_support'])[0]))+1
            for t in self.comparisons.values()if t.get('cap_support')is not None and t['cap_support'].any()),default=0)

    def position(self,image):
        return self.positions([image])[0]

    def positions(self,images):
        from piu_timeline.derived import call
        requests=[self.prepare(image)for image in images]
        localized=call('skinLocalization.resolveMany',requests)if requests else[]
        return [self.assemble(image,result)for image,result in zip(images,localized,strict=True)]

    def prepare(self,image):
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
        return comparison_input(image,self.bank,self.templates,lane,raw,height,self.scale,
                                self.comparisons,self.references)

    def assemble(self,image,result):
        name=image['template'];raw=image['y']*self.height
        measured,conflict=result['measurement'],result['conflict']
        anchor={'yPixels':raw,'uncertaintyPixels':0,
                'basis':{'kind':'image_reference_anchor','reference':{'kind':'sha256','value':self.references[name]}}}
        anchors=result['anchors']
        center=None
        if not conflict and 'native_cap_coordinate_uncertainty_pixels'in measured:
            center={'yPixels':measured['native_y_pixels'],
                    'uncertaintyPixels':measured['native_cap_coordinate_uncertainty_pixels'],
                    'basis':{'kind':'native_cap_center'}}
        measurement={'native_y_pixels':raw,'detected_y_pixels':raw,'image_anchor':[image['x'],image['y']],
                     'template':name,'cap_error':image['region_errors']['cap'],
                     'cap_reference_sha256':self.references[name],'classification_status':image['classification_status'],
                     **({'sampling_origin_pixels':image['sampling_origin_pixels']}if 'sampling_origin_pixels'in image else{}),
                     **measured,'trace':'frames.jsonl'}
        if conflict:measurement.update(native_cap_registration_status=conflict['reason'],registration_conflict=conflict)
        return {'anchor':anchor,'anchors':anchors,'center':center,'measurement':measurement,
                'coordinateSampling':'sampled_image_grid',
                'capRole':image.get('template_role',image['role'])
                    if image.get('classification_status')in('full_pattern','cap_role_pattern')else None}
