"""Connected hold kinds require source-local positive evidence and ownership."""
from copy import deepcopy
import unittest

from piu_timeline.play.holds.type_links import augment_types


def fixture():
    times=[.1+i*.02 for i in range(9)]
    frames=[{'playback_seconds':t,'source_pts_seconds':t+50}for t in times]
    notes=[{'lane':0,'status':'excluded','target_seconds':None,
            'points':[[t,200+40*i-200*t]for t in times]}for i in range(2)]
    proof={'decision':'connected_caps','head_note':0,'tail_note':1,
           'connected_source_pts_seconds':[f['source_pts_seconds']for f in frames],
           'gap_source_pts_seconds':[],'weak_source_pts_seconds':[],
           'visible_start_seconds':times[0],'visible_end_seconds':times[-1]}
    data={'notes':notes,'hold_analysis':{'holds':[],'unresolved_tracks':[{
        'cap_continuity':proof,'lane':0,'reason':'unresolved_hold_geometry',
        'visible_start_seconds':times[0],'visible_end_seconds':times[-1]}]}}
    observations=[{'kind':'hold','reason':'complete_cap_with_connected_color_stripe',
                   'source_pts_seconds':frames[3]['source_pts_seconds'],
                   'playback_seconds':times[3],'source_note':1,'trace':'appearance-features.npz'}]
    records=[{'note':0,'status':'unknown','observations':[]},
             {'note':1,'status':'hold','observations':observations}]
    return data,records,frames


class HoldTypeLinksTest(unittest.TestCase):
    def test_inferred_tail_stops_being_an_independent_tap_but_geometry_still_warns(self):
        from piu_timeline.play.holds.analysis import presentation
        from piu_timeline.play.exclusions import recognition_diagnostics
        data,records,frames=fixture()
        data.update(matches=[],combo_events=[],judgment_events=[],
                    visual_channels={'note_types':{'notes':augment_types(data,records,frames)}})
        before=deepcopy(data);view=presentation(data)
        self.assertEqual(data,before)
        self.assertEqual(view['notes'][1]['reason'],'observed_hold_tail_pending_geometry')
        self.assertEqual(view['matches'],[])
        self.assertIsNone(view['notes'][0]['target_seconds'])
        self.assertEqual(view['hold_analysis']['holds'],[])
        warnings=recognition_diagnostics(view,{'notes':{}})['warnings']
        self.assertTrue(any(w['reason']=='unresolved_hold_geometry'for w in warnings))
        self.assertTrue(any(w['reason']=='observed_hold_tail_pending_geometry'for w in warnings))

    def test_unknown_cap_uses_same_frame_hold_connection_without_restoring_timing(self):
        data,records,frames=fixture();before=deepcopy((data,records,frames))
        result=augment_types(data,records,frames)
        self.assertEqual((data,records,frames),before)
        self.assertEqual(result[0]['status'],'hold')
        observation=result[0]['observations'][0]
        self.assertEqual(observation['anchor_note'],1)
        self.assertEqual(observation['source_pts_seconds'],frames[3]['source_pts_seconds'])
        self.assertEqual(observation['anchor_observation'],records[1]['observations'][0])
        self.assertEqual(len(observation['connection_source_pts_seconds']),9)
        self.assertTrue(all(n['target_seconds']is None for n in data['notes']))
        self.assertEqual(augment_types(data,result,frames),result)
        data['hold_analysis']['unresolved_tracks']=[]
        self.assertEqual(augment_types(data,result,frames)[0]['status'],'unknown')

    def test_clear_tap_is_retained_as_a_conflict_even_in_another_frame(self):
        data,records,frames=fixture()
        tap={'kind':'tap','reason':'complete_cap_with_visible_separation_on_both_sides',
             'playback_seconds':.01,'source_pts_seconds':50.01}
        records[0]['observations'].append(tap)
        result=augment_types(data,records,frames)
        self.assertEqual(result[0]['status'],'conflict')
        self.assertIn(tap,result[0]['observations'])

    def test_unverified_connection_anchor_or_identity_cannot_infer_a_kind(self):
        for case in ('gap','short','few','missing_frame','missing_position','different_lane',
                     'unknown_anchor','foreign_pts','foreign_time','foreign_note',
                     'inferred_anchor','conflicting_anchor','competing_owner'):
            with self.subTest(case=case):
                data,records,frames=fixture();proof=data['hold_analysis']['unresolved_tracks'][0]['cap_continuity']
                if case=='gap':proof['gap_source_pts_seconds']=[50.15]
                elif case=='short':proof['visible_end_seconds']=.15
                elif case=='few':proof['connected_source_pts_seconds']=proof['connected_source_pts_seconds'][:7]
                elif case=='missing_frame':frames.pop()
                elif case=='missing_position':data['notes'][0]['points'].pop()
                elif case=='different_lane':data['notes'][0]['lane']=1
                elif case=='unknown_anchor':records[1]['observations'][0]['kind']='unknown'
                elif case=='foreign_pts':records[1]['observations'][0]['source_pts_seconds']=80
                elif case=='foreign_time':records[1]['observations'][0]['playback_seconds']+=1
                elif case=='foreign_note':records[1]['observations'][0]['source_note']=0
                elif case=='inferred_anchor':records[1]['observations'][0]['reason']='connected_to_native_hold_cap'
                elif case=='conflicting_anchor':records[1]['observations'].append({'kind':'tap','playback_seconds':0})
                else:
                    data['notes'].append(deepcopy(data['notes'][1]))
                    other=deepcopy(proof);other['tail_note']=2
                    data['hold_analysis']['unresolved_tracks'].append({'cap_continuity':other})
                self.assertEqual(augment_types(data,records,frames)[0]['status'],'unknown')
