"""A connected tail is not a new tap when chart endpoint reconstruction fails."""
from copy import deepcopy
import unittest

from piu_timeline.play.holds.analysis import presentation
from piu_timeline.play.holds.roles import observed_tail_roles
from piu_timeline.play.exclusions import recognition_diagnostics,exclusion_diagnostics


def fixture():
    notes=[{'lane':0,'status':'excluded','reason':'shared_timing_reconstruction_failed','target_seconds':None,
            'points':[[.1,200],[.2,180],[.3,160],[.4,140]]},
           {'lane':0,'status':'estimated','reason':None,'target_seconds':1.5,
            'points':[[.1,240],[.2,220],[.3,200],[.4,180]]}]
    proof={'decision':'connected_caps','head_note':0,'tail_note':1,
           'connected_source_pts_seconds':[100+i/60 for i in range(10)],
           'gap_source_pts_seconds':[],'weak_source_pts_seconds':[],
           'visible_start_seconds':.1,'visible_end_seconds':.3}
    return {'notes':notes,'matches':[{'note':1,'target_seconds':1.5}],
            'combo_events':[],'judgment_events':[],
            'visual_channels':{'note_types':{'notes':[
                {'note':i,'observations':[{'kind':'hold'}]}for i in (0,1)]}},
            'hold_analysis':{'holds':[],'unresolved_tracks':[{'lane':0,'reason':'unresolved_hold_geometry',
                'visible_start_seconds':.1,'visible_end_seconds':.4,'cap_continuity':proof}]}}


class HoldRolesTest(unittest.TestCase):
    def test_tail_role_survives_failed_head_timing_without_inventing_a_hold_or_press(self):
        data=fixture();original=deepcopy(data);view=presentation(data)
        self.assertEqual(data,original)
        self.assertEqual(view['notes'][1]['reason'],'observed_hold_tail_pending_geometry')
        self.assertEqual(view['matches'],[])
        self.assertEqual(view['hold_analysis']['holds'],[])
        self.assertIsNone(view['notes'][0]['target_seconds'])
        self.assertEqual(view['notes'][1]['target_seconds'],1.5)
        warnings=recognition_diagnostics(view,{'notes':{}})['warnings']
        self.assertTrue(any(w['reason']=='observed_hold_tail_pending_geometry'for w in warnings))
        self.assertTrue(any(w['reason']=='unresolved_hold_geometry'for w in warnings))
        self.assertTrue(any(w['reason']=='observed_hold_tail_pending_geometry'
                            for w in exclusion_diagnostics(data,view)['warnings']))

    def test_clear_tap_conflicting_ownership_and_weak_connection_cannot_remove_a_note(self):
        for kind in ('tap','weak','gap','owner'):
            data=fixture()
            if kind=='tap':data['visual_channels']['note_types']['notes'][1]['observations'].append({'kind':'tap'})
            if kind=='weak':data['hold_analysis']['unresolved_tracks'][0]['cap_continuity']['connected_source_pts_seconds']=[100]
            if kind=='gap':data['hold_analysis']['unresolved_tracks'][0]['cap_continuity']['gap_source_pts_seconds']=[100.04]
            if kind=='owner':
                data['notes'].append({**data['notes'][0],'lane':0})
                data['visual_channels']['note_types']['notes'].append({'note':2,'observations':[{'kind':'hold'}]})
                other=deepcopy(data['hold_analysis']['unresolved_tracks'][0]);other['cap_continuity']['head_note']=2
                data['hold_analysis']['unresolved_tracks'].append(other)
            with self.subTest(kind=kind):self.assertEqual(observed_tail_roles(data),[])
