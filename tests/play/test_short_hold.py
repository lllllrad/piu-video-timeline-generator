"""Short visible body spans require both independent moving cap identities."""
import copy
import unittest

from piu_timeline.play.holds.analysis import presentation
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

    def test_native_cap_ownership_is_independent_of_accepted_chart_timing(self):
        layout={'receptor_y':.2,'lanes':[{'x':.2+.1*i} for i in range(5)]}
        data={'game_roi':[0,0,325,200],'analysis_height':200,'layout':layout,'notes':[
            {'lane':2,'status':'excluded','target_seconds':None,'points':[[.8,130],[.85,120],[.9,110],[.95,100]]},
            {'lane':2,'status':'estimated','target_seconds':1.3,'points':[[.95,114]]}]}
        frame={'playback_seconds':.95,'source_pts_seconds':40.95,'bodies':[
            {'lane':2,'top':100,'bottom':175,'long':True,'stripe_support':.9,
             'top_visible':True,'tail_visible':True,'edge_convention':'connected_color'}]}
        geometry=HoldGeometry.from_analysis(data,325);before=copy.deepcopy(data)
        body=register_caps(data,[frame],geometry)[0]['bodies'][0]
        self.assertEqual(body['top_observed_cap_note'],0)
        self.assertNotIn('top_cap_note',body)  # A farther timed tap cannot steal this edge.
        from piu_timeline.play.note_types import body_type_observations
        proof=body_type_observations(data,[frame])[0][0]
        self.assertEqual(proof['kind'],'hold')
        self.assertEqual(proof['source_pts_seconds'],40.95)
        self.assertEqual(data,before)
        # An unsupported stationary candidate blocks a guessed owner, without
        # becoming positive hold evidence or an accepted endpoint timestamp.
        data['notes'][0]['points']=[[t,100] for t,y in data['notes'][0]['points']]
        body=register_caps(data,[frame],geometry)[0]['bodies'][0]
        self.assertEqual(body['top_unresolved_cap_note'],0)
        self.assertNotIn('top_cap_note',body)
        self.assertNotIn('top_observed_cap_note',body)

        hidden=copy.deepcopy(frame)
        hidden['bodies'][0].update(top_visible=False,top_cap_note=1,top_cap_y=114)
        refreshed=register_caps(data,[hidden],geometry)[0]['bodies'][0]
        self.assertNotIn('top_cap_note',refreshed)
        self.assertNotIn('top_observed_cap_note',refreshed)
        self.assertNotIn('top_unresolved_cap_note',refreshed)

    def test_body_projection_does_not_hide_a_failed_native_head_reconstruction(self):
        note={'lane':0,'status':'excluded','reason':'shared_timing_reconstruction_failed','target_seconds':None,
              'points':[[.5,160],[.6,140],[.7,120],[.8,100]],
              'timing_reconstruction':{'status':'failed','reason':'inconsistent_shared_motion'}}
        hold={'id':0,'lane':0,'start_range':[1,1.02],'end_range':[2,2.02],
              'start_censored':False,'end_censored':False,'head_note':None,'tail_note':None,
              'head_observation_note':0,'covered_notes':[],'last_body_seconds':2,
              'input':{'segments':[],'recognition_envelope':None}}
        data={'notes':[note],'matches':[],'combo_events':[],'judgment_events':[],'hold_analysis':{'holds':[hold]}}
        original=copy.deepcopy(data);view=presentation(data)
        projected=view['notes'][1]
        self.assertEqual(projected['source_head_observation'],0)
        self.assertEqual(projected['status'],'excluded')
        self.assertEqual(projected['reason'],'timing_reconstruction_failed')
        self.assertEqual(projected['timing_reconstruction'],note['timing_reconstruction'])
        self.assertEqual(view['matches'],[])
        self.assertEqual(data,original)
