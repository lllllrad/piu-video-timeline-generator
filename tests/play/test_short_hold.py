"""Short visible body spans require both independent moving cap identities."""
import copy
import unittest

from piu_timeline.play.holds.geometry import HoldGeometry, register_caps, resolve_geometry


class ShortHoldTest(unittest.TestCase):
    def fixture(self):
        layout={'receptor_y':.15,'lanes':[{'x':.38+.06*i} for i in range(5)]}
        data={'game_roi':[0,0,325,183],'analysis_width':325,'analysis_height':183,
              'layout':layout,'start_seconds':0,'end_seconds':2,'notes':[]}
        geometry=HoldGeometry.from_analysis(data,325)
        times=[.6+i/60 for i in range(4)]
        for target in (1,1.15):
            data['notes'].append({'lane':2,'status':'estimated','target_seconds':target,
                                 'prediction_uncertainty_seconds':.01,
                                 'points':[[.4+i/60,geometry.receptor+200*(target-(.4+i/60))] for i in range(43)
                                           if geometry.receptor+200*(target-(.4+i/60))>geometry.receptor+.85*geometry.spacing]})
        frames=[]
        for time in times:
            top=geometry.receptor+200*(1-time)-.1*geometry.spacing
            bottom=geometry.receptor+200*(1.15-time)+.1*geometry.spacing
            frames.append({'playback_seconds':time,'source_pts_seconds':40+time,'bodies':[
                {'lane':2,'top':top,'bottom':bottom,'long':True,'stripe_support':.9,
                 'edge_convention':'connected_color','top_visible':True,'tail_visible':True}]})
        registered=register_caps(data,frames,geometry)
        track=[{**f['bodies'][0],'time':f['playback_seconds'],'pts':f['source_pts_seconds']} for f in registered]
        return data,geometry,track

    def test_four_translating_body_frames_use_independent_native_cap_timings(self):
        data,geometry,track=self.fixture();before=copy.deepcopy(data)
        self.assertLess(track[-1]['time']-track[0]['time'],.08)
        hold=resolve_geometry(data,track,geometry)
        self.assertIsNotNone(hold)
        self.assertEqual((hold['head_note'],hold['tail_note']),(0,1))
        self.assertEqual(hold['start_range'],[.99,1.01])
        self.assertEqual(hold['end_range'],[1.14,1.16])
        self.assertEqual(hold['covered_notes'],[0,1])
        self.assertEqual(data,before)

    def test_weak_stripe_missing_edge_stationary_caps_and_capture_gaps_do_not_make_holds(self):
        data,geometry,original=self.fixture()
        for kind in ('weak','missing_tail','stationary','gap','three_frames'):
            track=copy.deepcopy(original)
            if kind=='weak':
                for p in track:p['stripe_support']=.75
            elif kind=='missing_tail':
                for p in track:p.pop('bottom_cap_note')
            elif kind=='stationary':
                for p in track:p['top_cap_y']=track[0]['top_cap_y']
            elif kind=='gap':track[-1]['time']+=.1
            else:track=track[:3]
            with self.subTest(kind=kind):self.assertIsNone(resolve_geometry(data,track,geometry))
