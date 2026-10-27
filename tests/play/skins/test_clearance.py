"""Native gap evidence complements cap RGB without using reference backgrounds."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from piu_timeline.play.skins.clearance import derive,validate_profile,FORMAT
from piu_timeline.play.skins.clearance_cache import prepare
from piu_timeline.play.skins.observations import observe


def scenario():
    cap={'id':'tap','role':'tap','lane_kind':0,'rgb':np.full((22,12,3),120,dtype='uint8'),
         'mask':np.ones((22,12),dtype=bool),'anchor_pixels':[6,11],'tap_clearance':True,
         'regions':[{'name':'cap','box':[0,6,12,16]},{'name':'clear_above','box':[1,0,11,4]},
                    {'name':'clear_below','box':[1,18,11,22]}]}
    bodies=[{'id':f'body-{i}','role':'hold_body','lane_kind':i,
             'rgb':np.full((4,8,3),color,dtype='uint8'),'mask':np.ones((4,8),dtype=bool),
             'anchor_pixels':[4,2],'regions':[{'name':'body','box':[0,0,8,4]}]}
            for i,color in enumerate(((0,100,255),(255,0,0),(255,220,0),(255,0,0),(0,100,255)))]
    bank={'skin':'test-skin','spacing_pixels':20,'templates':[cap,*bodies],
          'contract':{'synthetic':'fixed-pixels'},'anchor_registrations':{'tap':{}}}
    profile={'model':FORMAT['model'],'skin':bank['skin']}
    points=[(1+i*.025,150-i*5)for i in range(4)]
    data={'analysis_width':325,'analysis_height':200,'game_roi':[0,0,325,200],
          'layout':{'receptor_y':.05,'judgment_roi':[.15,.3,.4,.3],'combo_roi':[.15,.3,.4,.3],
                    'lanes':[{'x':.2+i*20/325,'color':color}
                     for i,color in enumerate(('blue','red','yellow','red','blue'))]},
          'notes':[{'lane':0,'points':points}], 'skin_detector':{'contract':{'bank':bank['contract']}},
          'segment_number':1,'start_seconds':1,'end_seconds':1.1,'frame_count':4,'media':{}}
    frames=[];samples=[]
    for t,y in points:
        image={'lane':0,'x':.2,'y':y/200,'role':'unknown','template_role':'tap','template':'tap',
               'skin':bank['skin'],'classification_status':'cap_only','bounds_pixels':[59,y-11,71,y+11],
               'region_errors':{'cap':.001,'clear_above':.2,'clear_below':.2}}
        frames.append({'playback_seconds':t,'source_pts_seconds':10+t,'skin_observations':[image]})
        planes={name:np.zeros((200,325),dtype=bool)for name in ('relaxed_blue','white','visible')}
        samples.append((10+t,t,planes,[]))
    return data,frames,samples,bank,profile


class NativeClearanceTest(unittest.TestCase):
    def test_positive_cap_and_measured_blank_bands_do_not_need_matching_background_rgb(self):
        data,frames,samples,bank,profile=scenario();original=deepcopy(frames)
        result=derive(data,frames,samples,bank,profile)
        self.assertEqual(result['validation']['validated_body_templates'],5)
        self.assertEqual(len(result['notes']['0']),4)
        self.assertEqual(frames,original)
        self.assertEqual(result['notes']['0'][0]['source_pts_seconds'],11.)
        observed=observe({**data,'skin_role_evidence':result},frames)
        self.assertEqual(observed['notes'][0]['status'],'tap')
        self.assertEqual(observed['notes'][0]['observations'][0]['kind'],'unknown')

    def test_connections_flashes_hud_clipping_and_unregistered_caps_are_unknown(self):
        for case in ('upper_connection','lower_connection','flash','hud','clipped','unregistered','static','sparse'):
            with self.subTest(case=case):
                data,frames,samples,bank,profile=scenario()
                if case=='unregistered':bank['anchor_registrations']={}
                if case in ('hud','clipped','static'):
                    points=[]
                    for i,frame in enumerate(frames):
                        y=(90-i*5)if case=='hud'else(10-i*5)if case=='clipped'else 150
                        o=frame['skin_observations'][0];o.update(y=y/200,bounds_pixels=[59,y-11,71,y+11])
                        points.append((frame['playback_seconds'],y))
                    data['notes'][0]['points']=points
                if case=='sparse':frames=frames[:3];samples=samples[:3]
                for frame,sample in zip(frames,samples,strict=True):
                    y=frame['skin_observations'][0]['bounds_pixels'][1]
                    if case.endswith('connection'):
                        yy=y+1 if case=='upper_connection'else y+19
                        sample[2]['relaxed_blue'][max(0,yy),65]=True
                    if case=='flash':sample[2]['white'][:]=True
                self.assertEqual(derive(data,frames,samples,bank,profile)['notes'],{})

    def test_new_clearance_does_not_erase_a_hold_observation(self):
        data,frames,samples,bank,profile=scenario();result=derive(data,frames,samples,bank,profile)
        frames[0]['skin_observations'][0].update(role='hold_start',template_role='hold_start',classification_status='full_pattern')
        observed=observe({**data,'skin_role_evidence':result},frames)
        self.assertEqual(observed['notes'][0]['status'],'conflict')

    def test_profile_must_explain_body_colors_and_native_pts_must_agree(self):
        for case in ('skin','body','missing_kind','timestamps','mask_geometry'):
            with self.subTest(case=case):
                data,frames,samples,bank,profile=scenario()
                if case=='skin':profile['skin']='different-skin'
                if case=='body':bank['templates'][1]['rgb'][:]=30
                if case=='missing_kind':bank['templates'].pop()
                if case=='timestamps':frames[1]['source_pts_seconds']+=.01
                if case=='mask_geometry':samples[0][2]['white']=samples[0][2]['white'][:,:-1]
                with self.assertRaises(ValueError):derive(data,frames,samples,bank,profile)

    def test_enabled_profile_without_features_fails_with_an_explicit_warning(self):
        data,*_=scenario()
        with tempfile.TemporaryDirectory()as temporary:
            source=Path(temporary)/'source';directory=source/'play/segment-001';directory.mkdir(parents=True)
            self.assertNotIn('skin_role_evidence',prepare(data,directory))
            (source/'note-skins.json').write_text(json.dumps({'schema':1,'profiles':[{
                'segments':[1],'role_clearance':{'model':FORMAT['model'],'skin':'test-skin'}}]}))
            result=prepare(data,directory)['skin_role_evidence']
            self.assertEqual(result['status'],'failed')
            self.assertEqual(result['warnings'][0]['reason'],'skin_clearance_profile_unavailable')
            self.assertEqual(result['notes'],{})

    def test_cached_clearance_cannot_survive_a_changed_source_or_frame_count(self):
        from piu_timeline.play.pixel_cache import FIELDS,FORMAT as PIXEL_FORMAT,source_contract
        data,frames,samples,bank,profile=scenario()
        data['skin_detector']['bank_path']='synthetic-bank'
        with tempfile.TemporaryDirectory()as temporary:
            source=Path(temporary)/'source';directory=source/'play/segment-001';directory.mkdir(parents=True)
            selection=source/'note-skins.json'
            selection.write_text(json.dumps({'schema':1,'profiles':[{'segments':[1],'role_clearance':profile}]}))
            (directory/'frames.jsonl').write_text(''.join(json.dumps(f)+'\n'for f in frames))
            native=directory/'native-features';native.mkdir()
            masks=np.zeros((4,len(FIELDS),200,325),dtype='uint8')
            np.savez_compressed(native/'00000.npz',fields=FIELDS,masks=np.packbits(masks,axis=-1),
                                pts=[s[0]for s in samples],times=[s[1]for s in samples],fractions=np.zeros((4,5)))
            (native/'manifest.json').write_text(json.dumps({'contract':{'format':PIXEL_FORMAT,'source':source_contract(data)},
                                                           'frame_count':4,'chunks':['00000.npz']}))
            with patch('piu_timeline.play.skins.bank.load_bank',return_value=bank):
                first=prepare(data,directory)['skin_role_evidence']
                self.assertEqual(first['status'],'available')
                self.assertIn('0',first['notes'])
                with patch('piu_timeline.play.skins.clearance_cache.derive',side_effect=AssertionError('must reuse')):
                    self.assertEqual(prepare(data,directory)['skin_role_evidence'],first)
                    retimed=deepcopy(data);retimed['notes'][0]['target_seconds']=99.
                    self.assertEqual(prepare(retimed,directory)['skin_role_evidence'],first)
                for case in ('source','frame_count','geometry'):
                    with self.subTest(case=case):
                        changed=deepcopy(data)
                        if case=='source':changed['media']={'path':'different-recording'}
                        elif case=='frame_count':changed['frame_count']=3
                        else:changed['layout']['receptor_y']=.08
                        result=prepare(changed,directory)['skin_role_evidence']
                        self.assertEqual(result['status'],'failed')
                        self.assertEqual(result['notes'],{})
                selection.unlink()
                self.assertNotIn('skin_role_evidence',prepare({**data,'skin_role_evidence':first},directory))
