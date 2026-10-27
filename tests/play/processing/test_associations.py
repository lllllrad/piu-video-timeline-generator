"""Disputed refresh assignments remain provenance, never confirmation or ownership."""
from copy import deepcopy
import unittest

from piu_timeline.play.associations import partition,disputed_refresh
from piu_timeline.play.recovery import recover_rows
from piu_timeline.play.holds.analysis import presentation
from piu_timeline.play.deferred_words import recover
from tests.play.holds.fixtures import scenario
from piu_timeline.play.judgments import cache_contracts


def assignment():
    return {'note':0,'target_seconds':1.,'judgment_event':0,'judgment_label':'GREAT',
            'observation_lower_seconds':1.02,'observation_upper_seconds':1.04,
            'processing_conflict':True}


class AssociationQuarantineTest(unittest.TestCase):
    def test_quarantine_does_not_change_native_word_source_contract(self):
        bad={**assignment(),'target_seconds':.9,'combo_event':6,
             'combo_lower_seconds':.91,'combo_upper_seconds':.92}
        good={'note':1,'target_seconds':1.,'combo_event':7,'combo_lower_seconds':1.02,'combo_upper_seconds':1.04}
        data={'notes':[{'target_seconds':.9},{'target_seconds':1.}],'matches':[bad,good]}
        original=cache_contracts(data,[]);view=partition(data)
        self.assertEqual(cache_contracts(view,[]),original)
        view['conflicted_matches'][0]={**bad,'combo_lower_seconds':.9}
        self.assertNotEqual(cache_contracts(view,[])['association'],original['association'])
        self.assertEqual(cache_contracts(view,[])['observations'],original['observations'])

    def test_partition_preserves_provenance_updates_counts_and_is_idempotent(self):
        data={'matches':[assignment()],
              'coverage':{'timed_note_heads':1,'judgment_labeled_note_heads':1,'visible_note_heads':2}}
        original=deepcopy(data);result=partition(data)
        self.assertEqual(result['matches'],[])
        self.assertEqual(result['conflicted_matches'],[assignment()])
        self.assertEqual(result['coverage'],{'timed_note_heads':0,'judgment_labeled_note_heads':0,'visible_note_heads':2})
        self.assertEqual(partition(result),result);self.assertEqual(data,original)

    def test_rejected_note_cannot_recover_same_refresh_but_another_lane_can_own_it(self):
        note={'status':'estimated','lane':0,'target_seconds':1.,'prediction_uncertainty_seconds':.01}
        run={'lane':1,'lit':True,'frames':4,'start_seconds':1.02,'end_seconds':1.08,
             'onset_range':[1.,1.02],'onset_source_pts_seconds':[11.,11.02]}
        data={'notes':[note,{**note,'lane':1,'target_seconds':1.03}],
              'matches':[assignment()],'combo_events':[],
              'judgment_events':[{'label':'GREAT','delta':1,'lower_seconds':1.02,'upper_seconds':1.04}],
              'hold_analysis':{'holds':[],'receptor_runs':[run]}}
        original=deepcopy(data);matches,indices=recover_rows(data)
        self.assertEqual(indices,[1]);self.assertEqual([m['note']for m in matches],[1])
        self.assertEqual(matches[0]['judgment_event'],0)
        self.assertEqual(matches[0]['observation_upper_seconds'],1.04)
        self.assertEqual(data,original)

    def test_same_bracket_under_another_reader_cannot_rehabilitate_disputed_assignment(self):
        data=partition({'matches':[assignment()]})
        raw={'source':'counter_frames','event':7,'lower_seconds':1.02,'upper_seconds':1.04}
        self.assertTrue(disputed_refresh(data,0,[raw]))
        self.assertFalse(disputed_refresh(data,1,[raw]))
        self.assertFalse(disputed_refresh(data,0,[{**raw,'lower_seconds':1.05,'upper_seconds':1.067}]))
        self.assertFalse(disputed_refresh(data,0,[{**raw,'source':'judgment','event':0,
                                                   'lower_seconds':1.05,'upper_seconds':1.067}]))

    def test_pre_hold_pass_keeps_a_disputed_word_out_of_confirmed_matches(self):
        data=scenario();event=data['judgment_events'][0]
        data['matches']=[{**assignment(),'target_seconds':1.01,
                         'observation_lower_seconds':event['lower_seconds'],
                         'observation_upper_seconds':event['upper_seconds']}]
        matches,indices=recover(data,data['notes'],data['matches'],{1,2})
        self.assertEqual(matches,[]);self.assertEqual(indices,[])
        result=presentation(data)
        self.assertEqual(result['matches'],[]);self.assertEqual(len(result['conflicted_matches']),1)
        self.assertNotEqual(result['judgment_events'][0]['status'],'matched')
        self.assertEqual(result['coverage']['timed_note_heads'],0)
