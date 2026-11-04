"""A connector needs measured body pixels, never a nearby body bounding box."""
from copy import deepcopy
import unittest

import numpy as np

from piu_timeline.play.skins.connections import body_connections


def scene(scale=1):
    box=lambda values:[int(x*scale)for x in values]
    cap={'support':np.ones((24*scale,12*scale),dtype=bool),'regions':[
        {'name':'connection','box':box([4,14,8,18]),'mask':np.ones((4*scale,4*scale),dtype='uint8')}]}
    body={'support':np.ones((2*scale,4*scale),dtype=bool),'regions':[
        {'name':'body','box':box([0,0,4,2]),'mask':np.ones((2*scale,4*scale),dtype='uint8')}]}
    models={'start':cap,'body':body}
    image={'lane':0,'role':'unknown','template_role':'hold_start','template':'start',
           'classification_status':'cap_only','bounds_pixels':box([44,41,56,65])}
    bodies=[{'lane':0,'role':'hold_body','template':'body','classification_status':'full_pattern',
             'bounds_pixels':box([48,55+i*2,52,57+i*2]),'region_errors':{'body':.001}}for i in range(2)]
    return {'analysis_width':100*scale,'analysis_height':100*scale},{'skin_observations':[image,*bodies]},models


class BodyConnectionTest(unittest.TestCase):
    def test_native_body_comparisons_reach_the_independent_role_channel(self):
        from tests.play.skins.test_clearance import scenario
        from piu_timeline.play.skins.clearance import derive
        from piu_timeline.play.skins.detector import SkinDetector
        from piu_timeline.play.skins.observations import observe
        data,frames,samples,bank,profile=scenario()
        start=deepcopy(bank['templates'][0]);start.update(id='start',role='hold_start')
        start['regions']=[start['regions'][0],{'name':'connection','box':[4,16,8,20]}]
        bank['templates'].append(start)
        model=next(t for t in SkinDetector(bank,data['layout'],325,200).templates if t['id']=='start')
        for frame,sample in zip(frames,samples,strict=True):
            image=frame['skin_observations'][0];y=round(image['y']*200)
            left,top=round(65-model['anchor'][0]),round(y-model['anchor'][1])
            h,w=model['support'].shape
            image['alternatives']=[{**image,'template':'start','template_role':'hold_start',
                'region_errors':{'cap':.001,'connection':.2},'bounds_pixels':[left,top,left+w,top+h]}]
            frame['skin_observations'].append({'lane':0,'role':'hold_body','template':'body-0',
                'classification_status':'full_pattern','bounds_pixels':[61,y+5,69,y+9],
                'x':.2,'y':(y+7)/200,'region_errors':{'body':.001}})
            sample[2]['relaxed_blue'][y+5:y+9,61:69]=True
        result=derive(data,frames,samples,bank,profile)
        self.assertEqual(result['counts']['connected_hold_roles'],1)
        self.assertEqual(result['counts']['qualified_clearance_notes'],0)
        channel=observe({**data,'skin_role_evidence':result},frames)
        self.assertEqual(channel['notes'][0]['status'],'hold')
        self.assertTrue(any(o['role']=='hold_start'for o in channel['notes'][0]['observations']))
        for frame in frames[:3]:frame['skin_observations'].pop()
        result=derive(data,frames,samples,bank,profile)
        self.assertEqual(len(result['notes']['0']),1)
        self.assertEqual(observe({**data,'skin_role_evidence':result},frames)['notes'][0]['status'],'hold')

    def test_independent_body_comparisons_can_jointly_cover_a_failed_endpoint_connector(self):
        for scale in (1,2,3):
            data,frame,models=scene(scale);original=deepcopy(frame)
            proof=body_connections(data,frame,models)
            self.assertEqual(len(proof),1)
            self.assertEqual(proof[0][2]['role'],'hold_start')
            self.assertEqual(proof[0][2]['connector_supported_pixels'],16*scale*scale)
            self.assertEqual(proof[0][2]['body_comparisons'],[
                {'observation':1,'comparison':0},{'observation':2,'comparison':0}])
            self.assertEqual(frame,original)
            # The same measured relation works above a hold-end cap.
            frame['skin_observations'][0]['template_role']='hold_end'
            self.assertEqual(body_connections(data,frame,models)[0][2]['role'],'hold_end')

    def test_partial_or_wrong_lane_body_support_cannot_bridge_even_one_unmeasured_pixel(self):
        for case in ('gap','horizontal','wrong_lane','bad_rgb','cap_artwork','partial_mask'):
            with self.subTest(case=case):
                data,frame,models=scene();body=frame['skin_observations'][1]
                if case=='gap':frame['skin_observations'].pop(1)
                elif case=='horizontal':body['bounds_pixels']=[49,55,53,57]
                elif case=='wrong_lane':body['lane']=1
                elif case=='bad_rgb':body['region_errors']['body']=.02
                elif case=='cap_artwork':body['cap_subfeature']={'measured_inside_cap':True}
                else:models['body']['regions'][0]['mask'][0,0]=0
                self.assertEqual(body_connections(data,frame,models),[])

    def test_ungrouped_body_alternatives_keep_their_actual_compared_pixel_support(self):
        data,frame,models=scene();first=frame['skin_observations'][1]
        first['alternatives']=[frame['skin_observations'].pop()]
        self.assertEqual(len(body_connections(data,frame,models)),1)
        first['alternatives'][0]['bounds_pixels']=[48,58,52,60]
        self.assertEqual(body_connections(data,frame,models),[])
