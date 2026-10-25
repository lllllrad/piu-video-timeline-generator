from copy import deepcopy
from types import SimpleNamespace
import unittest

from piu_timeline.play.analysis import resolve_timing
from piu_timeline.play.holds.analysis import presentation


def evidence(delta=1):
    notes=[{'status':'estimated','lane':0,'target_seconds':9,'prediction_uncertainty_seconds':.01},
           {'status':'estimated','lane':1,'target_seconds':10,'prediction_uncertainty_seconds':.01}]
    tracker=SimpleNamespace(finish=lambda:notes,unsupported_intervals=[{'start_seconds':9,'end_seconds':11}])
    combo=SimpleNamespace(events=[{'status':'candidate','delta':delta,'lower_seconds':9.99,'upper_seconds':10.01}])
    data=resolve_timing(tracker,combo,0)
    data['hold_analysis']={'holds':[{'id':0,'lane':0,'head_note':0,'covered_notes':[0],
                           'start_range':[9,9.02],'end_range':[11,11.02],'start_censored':False,
                           'end_censored':False,'input':{'segments':[]}}],
                          'receptor_runs':[{'lane':1,'lit':True,'frames':3,'start_seconds':10.03,
                                            'end_seconds':10.08,'previous_seconds':10.01,'previous_lit':None,
                                            'onset_range':[9.98,10.03],'onset_source_pts_seconds':[109.98,110.03]}]}
    return data


class DeferredTapTest(unittest.TestCase):
    def test_other_lane_tap_is_not_lost_to_global_hold_veto(self):
        data=evidence();original=deepcopy(data)
        self.assertEqual(data['matches'],[])
        self.assertEqual([m['note'] for m in data['deferred_matches']],[1])
        result=presentation(data)
        self.assertEqual([m['note'] for m in result['matches']],[1])
        match=result['matches'][0]
        self.assertEqual([match['observation_lower_seconds'],match['observation_upper_seconds']],[9.99,10.01])
        self.assertEqual(result['recovered_dense_notes'],[1])
        self.assertEqual(result['combo_events'][0]['status'],'matched')
        self.assertEqual(data,original)

    def test_dense_flag_without_a_reconstructed_hold_still_requires_independent_onset(self):
        data=evidence();data['hold_analysis']['holds']=[]
        self.assertEqual(presentation(data)['recovered_dense_notes'],[1])
        data['hold_analysis']['receptor_runs'][0]['onset_range']=None
        self.assertEqual(presentation(data)['matches'],[])

    def test_sustained_or_other_lane_light_cannot_turn_hold_tick_into_a_tap(self):
        for change in ({'onset_range':None},{'lane':0},{'onset_range':[9.5,9.52]}):
            with self.subTest(change=change):
                data=evidence();data['hold_analysis']['receptor_runs'][0].update(change)
                self.assertEqual(presentation(data)['matches'],[])

    def test_competing_word_row_prevents_recovery_from_the_same_refresh(self):
        data=evidence()
        data['notes'].append({'status':'estimated','lane':2,'target_seconds':10.09,'prediction_uncertainty_seconds':.01})
        data['matches']=[{'note':2,'target_seconds':10.09,'combo_event':None,'judgment_event':0,
                         'observation_lower_seconds':9.99,'observation_upper_seconds':10.01}]
        result=presentation(data)
        self.assertNotIn(1,result['recovered_dense_notes'])

    def test_skipped_counter_including_multiple_rows_is_not_recovered_as_one_tap(self):
        data=evidence()
        data['combo_events'][0]['delta']=2
        self.assertEqual(presentation(data)['matches'],[])
