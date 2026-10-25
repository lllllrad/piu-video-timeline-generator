"""Concrete effects preserve native counts, ranges, grades and strict ownership."""
from copy import deepcopy
import unittest

from piu_timeline.play.gimmicks import apply_gimmicks
from piu_timeline.play.ranges import timing_ranges


def fixture():
    return {'notes':[{'status':'estimated','target_seconds':1.,'lane':0,'prediction_uncertainty_seconds':.01}],
            'matches':[], 'combo_events':[{'before':20,'after':30,'delta':10,'lower_seconds':.99,
                                          'upper_seconds':1.01,'status':'excluded','reason':'ambiguous_note_or_combo_association'}],
            'hold_analysis':{'holds':[],'receptor_runs':[{'lane':0,'lit':True,'frames':3,
                              'start_seconds':1.01,'end_seconds':1.05,'onset_range':[.99,1.01],
                              'onset_source_pts_seconds':[10.99,11.01]}]},
            'judgment_events':[], 'chart_policy':{'regions':[],'gimmick_candidates':[
                {'id':'ten','kind':'suspected_multi_increment','review_status':'pending','combo_increment':10,
                 'playback_start_seconds':.9,'playback_end_seconds':1.1}]}}


class GimmickProcessingTest(unittest.TestCase):
    def test_pending_plus_ten_uses_one_independently_observed_row_without_fabricating_grades(self):
        data=fixture();native=deepcopy(data);view=apply_gimmicks(data)
        self.assertEqual(data,native)
        self.assertEqual(view['combo_events'][0]['delta'],10)
        self.assertEqual(view['combo_events'][0]['judged_row_count'],1)
        self.assertEqual([m['note'] for m in view['matches']],[0])
        match=view['matches'][0]
        self.assertEqual((match['combo_lower_seconds'],match['combo_upper_seconds']),(.99,1.01))
        self.assertEqual(match['aggregate_row_count'],1)
        self.assertNotIn('judgment_label',match)
        self.assertEqual(timing_ranges(view)['notes'][0]['status'],'matched')

    def test_wrong_increment_missing_lane_evidence_hold_miss_or_rejected_policy_cannot_make_a_press(self):
        for kind in ('wrong_increment','gap','missing_onset','hold','miss','rejected','outside','conflicting'):
            with self.subTest(kind=kind):
                data=fixture()
                if kind=='wrong_increment':data['combo_events'][0]['delta']=5
                if kind=='gap':data['combo_events'][0]['lower_seconds']=.8
                if kind=='missing_onset':data['hold_analysis']['receptor_runs']=[]
                if kind=='hold':data['hold_analysis']['holds']=[{'start_range':[.9,.91],'end_range':[1.2,1.21]}]
                if kind=='miss':data['miss_candidates']=[{'note':0}]
                if kind=='rejected':data['chart_policy']['gimmick_candidates'][0]['review_status']='rejected'
                if kind=='conflicting':data['chart_policy']['gimmick_candidates'].append(
                    {**data['chart_policy']['gimmick_candidates'][0],'id':'other','combo_increment':5})
                if kind=='outside':data['chart_policy']['gimmick_candidates'][0]['playback_end_seconds']=1.01
                self.assertEqual(apply_gimmicks(data)['matches'],[])

    def test_incorrect_counter_row_allocation_is_removed_but_independent_word_survives(self):
        data=fixture();data['hold_analysis']['receptor_runs']=[]
        data['judgment_events']=[{'label':'GREAT','lower_seconds':.995,'upper_seconds':1.005}]
        data['matches']=[{'note':0,'target_seconds':1.,'combo_event':0,'judgment_event':0,
                          'judgment_label':'GREAT','combo_lower_seconds':.99,'combo_upper_seconds':1.01}]
        result=apply_gimmicks(data)['matches'][0]
        self.assertIsNone(result['combo_event'])
        self.assertEqual(result['judgment_label'],'GREAT')
        self.assertEqual((result['observation_lower_seconds'],result['observation_upper_seconds']),(.995,1.005))
        data['matches'][0]['judgment_event']=None
        self.assertEqual(apply_gimmicks(data)['matches'],[])

    def test_visibility_modifier_changes_loss_semantics_without_suppressing_timing_or_type(self):
        data=fixture();data['combo_events']=[]
        effect=data['chart_policy']['gimmick_candidates'][0]
        effect.update(kind='suspected_visibility_modifier',playback_start_seconds=.8,playback_end_seconds=1.2)
        record={'note':0,'id':'processing:0','status':'unresolved','reason':'pre_receptor_visibility_boundary',
                'samples':[], 'visibility_loss':{'source_pts_seconds':[10.9,10.92]}}
        data['visual_channels']={'processing':{'notes':[record],
             'visibility_boundaries':[{'notes':[0],'playback_range':[.9,1.1]}]}}
        native=deepcopy(data);view=apply_gimmicks(data)
        self.assertEqual(data,native)
        processed=view['visual_channels']['processing']['notes'][0]
        self.assertEqual(processed['status'],'visibility_modified')
        self.assertEqual(processed['native_status'],'unresolved')
        self.assertEqual(processed['visibility_loss']['source_pts_seconds'],[10.9,10.92])
        self.assertEqual(view['matches'],[])
        self.assertEqual(view['chart_policy']['regions'],[])
        from piu_timeline.play.exclusions import recognition_diagnostics
        view['note_type_diagnostics']=[{'note':0,'lane':0,'reason':'note_type_conflict',
                                       'visible_start_seconds':.9,'visible_end_seconds':1.1}]
        warnings=recognition_diagnostics(view,{'notes':{'0':{'status':'unknown','target_range':[.99,1.01]}}})
        self.assertEqual({r['reason'] for r in warnings['warnings']},
                         {'note_type_conflict','timing_evidence_unresolved'})
        self.assertEqual(warnings['chart_exceptions'],[])
        effect['review_status']='rejected'
        self.assertEqual(apply_gimmicks(data)['visual_channels']['processing']['notes'][0],record)

    def test_unknown_effect_is_visible_without_generic_exemptions(self):
        data=fixture();data['chart_policy']['gimmick_candidates'][0]['kind']='unimplemented'
        result=apply_gimmicks(data)
        self.assertEqual(result['chart_policy']['unsupported_gimmicks'],['ten'])
        self.assertEqual(result['chart_policy']['regions'],[])
        self.assertEqual(result['matches'],[])
