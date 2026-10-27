"""Image endpoints need one uniquely covered body, never a second tap."""
from copy import deepcopy
import unittest

from piu_timeline.play.skins.holds import reconstruct_images
from piu_timeline.play.skins.observations import observe, tail_roles


def scenario():
    layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1,'color':'blue'}for i in range(5)]}
    data={'analysis_width':200,'analysis_height':300,'start_seconds':0,'end_seconds':2,
          'game_roi':[0,0,200,300],'layout':layout,'skin_detector':{'contract':{'schema':1}},'notes':[]}
    native,receptors=[],[]
    for i in range(10):
        t=i*.02;y=100-100*t
        observations=[]
        for role,anchor,bounds in [('hold_start',y,[10,y-10,30,y+25]),
                                   ('hold_end',y+60,[10,y+35,30,y+70]),
                                   ('hold_body',y+35,[16,y+20,24,y+50])]:
            observations.append({'lane':0,'x':.1,'y':anchor/300,'role':role,'template':role,
                                 'skin':'synthetic','region_errors':{'cap':0.,'connection':0.},'bounds_pixels':bounds})
        native.append({'playback_seconds':t,'source_pts_seconds':t+30,'skin_observations':observations})
        receptors.append({'playback_seconds':t,'source_pts_seconds':t+30,'receptor_lit':[None]*5})
    for offset,target in [(0,.85),(60,1.45)]:
        data['notes'].append({'lane':0,'status':'estimated','points':[[i*.02,100-2*i+offset]for i in range(10)],
                              'target_seconds':target,'prediction_uncertainty_seconds':.01,
                              'velocity_pixels_per_second':-100})
    return data,native,receptors


class ImageHoldTest(unittest.TestCase):
    def test_start_body_and_end_images_form_one_held_interval_without_color_components(self):
        data,native,receptors=scenario();original=deepcopy((data,native,receptors));warnings=[]
        holds=reconstruct_images(data,receptors,native,warnings)
        self.assertEqual(len(holds),1)
        hold=holds[0]
        self.assertEqual((hold['head_note'],hold['tail_note']),(0,1))
        self.assertEqual(hold['covered_notes'],[0,1])
        self.assertEqual(len(hold['image_connection_evidence']),10)
        self.assertEqual(hold['source_pts_range'],[30,30.18])
        self.assertEqual(warnings,[])
        self.assertEqual((data,native,receptors),original)

    def test_one_uncovered_frame_or_a_conflicting_tap_image_prevents_complete_hold(self):
        for case in ('body_gap','tap_conflict','failed_clock'):
            data,native,receptors=scenario()
            if case=='body_gap':native[3]['skin_observations'].pop()
            elif case=='tap_conflict':native[3]['skin_observations'][1]['role']='tap'
            else:data['notes'][0]['status']='excluded'
            warnings=[]
            self.assertEqual(reconstruct_images(data,receptors,native,warnings),[])
            self.assertTrue(warnings)

    def test_a_tail_image_needs_no_tap_or_input_at_its_cap_and_conflicts_stay_explicit(self):
        data,native,_=scenario();data['visual_channels']={'note_types':observe(data,native)}
        roles=tail_roles(data)
        self.assertEqual([r['tail_note']for r in roles],[1])
        self.assertTrue(roles[0]['image_evidence'])
        native[0]['skin_observations'][1]['role']='tap'
        data['visual_channels']['note_types']=observe(data,native)
        self.assertEqual(tail_roles(data),[])
        self.assertEqual(data['visual_channels']['note_types']['notes'][1]['status'],'conflict')
