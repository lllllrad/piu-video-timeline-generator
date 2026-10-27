"""Aggregate HUD updates need a complete set of independent, exclusive tap observations."""
from copy import deepcopy
import unittest

from piu_timeline.play.aggregates import recover_aggregates
from piu_timeline.play.holds.analysis import presentation


def evidence():
    return {'notes':[{'status':'estimated','lane':i,'target_seconds':t,'prediction_uncertainty_seconds':.01}
                     for i,t in enumerate((1.,1.1))],
            'matches':[{'note':0,'target_seconds':1.,'combo_event':None,'judgment_event':0,
                        'observation_lower_seconds':1.01,'observation_upper_seconds':1.02,
                        'judgment_label':'GREAT','evidence_source':'judgment'}],
            'combo_events':[{'delta':2,'lower_seconds':1.,'upper_seconds':1.08,
                             'before':10,'after':12,'status':'excluded','reason':'ambiguous_note_or_combo_association'}],
            'judgment_events':[{'label':'GREAT','delta':1,'lower_seconds':1.01,'upper_seconds':1.02,'status':'matched'}],
            'hold_analysis':{'holds':[], 'receptor_runs':[
                {'lane':i,'lit':True,'frames':3,'start_seconds':hi,'end_seconds':hi+.04,
                 'onset_range':[lo,hi],'onset_source_pts_seconds':[100+lo,100+hi]}
                for i,(lo,hi) in enumerate(((1.,1.01),(1.06,1.08)))]}}


class AggregateRecoveryTest(unittest.TestCase):
    def test_unowned_image_tile_summary_is_not_a_continuous_hold_at_the_receptors(self):
        from piu_timeline.play.skins.held import FORMAT
        data=evidence()
        data.update(skin_detector={'contract':{'held_body':FORMAT},'missing_template_roles':[]},unsupported_intervals=[])
        warning={'visible_start_seconds':.1,'visible_end_seconds':2.,
                 'failure_detail':'skin_body_images_without_complete_endpoint_ownership',
                 'image_evidence':[{'role':'hold_body','playback_seconds':t}for t in(.1,2.)]}
        data['hold_analysis']['unresolved_tracks']=[warning]
        original=deepcopy(data)
        matches,recovered=recover_aggregates(data)
        self.assertEqual(recovered,[1]);self.assertEqual(data,original)
        self.assertEqual(matches[1]['aggregate_body_risk_basis'],'native_receptor_body_regions')
        for case in ('active_body','missing_role','old_detector','connected_body','missing_evidence'):
            with self.subTest(case=case):
                changed=deepcopy(data)
                if case=='active_body':changed['unsupported_intervals']=[{'start_seconds':1.,'end_seconds':1.1}]
                elif case=='missing_role':changed['skin_detector']['missing_template_roles']=[{'role':'hold_body'}]
                elif case=='old_detector':changed['skin_detector']['contract']['held_body']={}
                elif case=='connected_body':changed['hold_analysis']['unresolved_tracks'][0]['failure_detail']='unresolved_connected_body'
                else:changed['hold_analysis']['unresolved_tracks'][0].pop('image_evidence')
                self.assertEqual(recover_aggregates(changed)[1],[])

    def test_distinct_rows_can_be_pressed_together_with_independent_lane_onsets(self):
        data=evidence();data['matches']=[];data['judgment_events']=[]
        data['combo_events'][0].update(lower_seconds=1.04,upper_seconds=1.06)
        for run in data['hold_analysis']['receptor_runs']:
            run.update(onset_range=[1.04,1.06],onset_source_pts_seconds=[101.04,101.06],start_seconds=1.06,end_seconds=1.1)
        matches,recovered=recover_aggregates(data)
        self.assertEqual(recovered,[0,1])
        self.assertTrue(all(m['observation_lower_seconds']==1.04 and m['observation_upper_seconds']==1.06 for m in matches))

    def test_independent_taps_keep_aggregate_range_and_existing_narrow_word_grade(self):
        data=evidence(); original=deepcopy(data)
        matches,recovered=recover_aggregates(data)
        self.assertEqual(data,original)
        self.assertEqual(recovered,[1])
        self.assertEqual(matches[0]['observation_lower_seconds'],1.01)
        self.assertEqual(matches[0]['observation_upper_seconds'],1.02)
        self.assertEqual(matches[0]['judgment_label'],'GREAT')
        self.assertEqual(matches[0]['evidence_source'],'combo+lane_onset+judgment')
        self.assertEqual(matches[1]['observation_lower_seconds'],1.)
        self.assertEqual(matches[1]['observation_upper_seconds'],1.08)
        self.assertEqual(matches[1]['aggregate_lane_onset_source_pts_seconds'],[101.06,101.08])
        self.assertNotIn('judgment_label',matches[1])
        self.assertTrue(all(m['combo_event']==0 and m['aggregate_row_count']==2 for m in matches))
        result=presentation(data)
        self.assertEqual({m['note'] for m in result['matches']},{0,1})
        self.assertEqual(result['combo_events'][0]['status'],'matched')
        self.assertEqual(result['combo_events'][0]['reason'],'aggregate_counter_with_exclusive_lane_onsets')
        self.assertEqual(result['coverage']['timed_note_heads'],2)

    def test_exact_100ms_aggregate_window_is_inclusive_without_widening_it(self):
        data=evidence();data['combo_events'][0]['upper_seconds']=1.1
        matches,recovered=recover_aggregates(data)
        self.assertEqual(recovered,[1])
        self.assertEqual(matches[1]['observation_upper_seconds'],1.1)
        data['combo_events'][0]['upper_seconds']+=.00001
        self.assertEqual(recover_aggregates(data)[1],[])

    def test_static_unknown_shared_missing_and_foreign_owned_onsets_cannot_fill_counter(self):
        for kind in ('static','unknown','single_frame','missing','shared','owned'):
            with self.subTest(kind=kind):
                data=evidence();runs=data['hold_analysis']['receptor_runs']
                if kind=='static':runs[1]['onset_range']=None
                if kind=='unknown':runs[1]['lit']=None
                if kind=='single_frame':runs[1]['frames']=1
                if kind=='missing':runs.pop()
                if kind=='shared':
                    data['notes'][1]['lane']=0;runs[0]['onset_range']=[1.,1.08]
                if kind=='owned':
                    data['notes'].append({'status':'estimated','lane':1,'target_seconds':1.5,'prediction_uncertainty_seconds':.01})
                    data['matches'].append({'note':2,'target_seconds':1.5,'combo_event':2,
                                            'observation_lower_seconds':1.06,'observation_upper_seconds':1.08})
                self.assertEqual(recover_aggregates(data)[1],[])

    def test_holds_unresolved_bodies_miss_and_extra_rows_remain_ambiguous(self):
        for kind in ('hold','unresolved_body','miss','possible_miss','extra_row','chord','wrong_count','gap','foreign_counter','foreign_word','uncertain_target'):
            with self.subTest(kind=kind):
                data=evidence()
                if kind=='hold':data['hold_analysis']['holds']=[{'start_range':[.5,.6],'end_range':[2.,2.1]}]
                if kind=='unresolved_body':data['hold_analysis']['unresolved_tracks']=[{'visible_start_seconds':.7,'visible_end_seconds':.9}]
                if kind=='miss':data['judgment_events'].append({'label':'MISS','lower_seconds':1.03,'upper_seconds':1.04})
                if kind=='possible_miss':data['miss_candidates']=[{'note':1}]
                if kind in ('extra_row','chord'):
                    data['notes'].append({'status':'estimated','lane':2,'target_seconds':1.05 if kind=='extra_row' else 1.1,'prediction_uncertainty_seconds':.01})
                if kind=='wrong_count':data['combo_events'][0]['delta']=3
                if kind=='gap':data['combo_events'][0]['lower_seconds']=.8
                if kind=='foreign_counter':data['matches'][0]['combo_event']=2
                if kind=='uncertain_target':data['notes'][1]['prediction_uncertainty_seconds']=.08
                if kind=='foreign_word':
                    data['notes'].append({'status':'estimated','lane':2,'target_seconds':1.4,'prediction_uncertainty_seconds':.01})
                    data['matches'].append({'note':2,'target_seconds':1.4,'combo_event':None,'judgment_event':1,
                                            'observation_lower_seconds':1.04,'observation_upper_seconds':1.05})
                self.assertEqual(recover_aggregates(data)[1],[])

    def test_competing_counter_updates_cannot_claim_the_same_taps(self):
        data=evidence();data['combo_events'].append(dict(data['combo_events'][0]))
        self.assertEqual(recover_aggregates(data)[1],[])
