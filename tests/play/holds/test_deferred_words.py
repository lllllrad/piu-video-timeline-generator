"""A confirmed early word can precede a fully accounted future hold."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from piu_timeline.play.deferred_words import recover,METHOD
from piu_timeline.play.holds.analysis import presentation
from piu_timeline.play.skins.held import FORMAT


def scenario():
    notes=[{'lane':0,'status':'estimated','type_status':'tap','target_seconds':1.01,'prediction_uncertainty_seconds':.005},
           {'lane':1,'status':'estimated','target_seconds':1.15,'prediction_uncertainty_seconds':.01,
            'velocity_pixels_per_second':-500},
           {'lane':1,'status':'estimated','target_seconds':1.35,'prediction_uncertainty_seconds':.01,
            'velocity_pixels_per_second':-500}]
    hold={'id':0,'head_note':1,'tail_note':2,'covered_notes':[1,2],'lane':1,
          'start_range':[1.14,1.16],'end_range':[1.34,1.36],'start_censored':False,'end_censored':False,
          'body_frames':8,'body_evidence':'skin_start_body_end_images','input':{'segments':[]}}
    warning={'hold':0,'note':1,'tail_note':2,'lane':1,
             'failure_detail':'known_hold_image_connection_not_observed_in_clear_frames',
             'visible_start_seconds':.8,'visible_end_seconds':1.12}
    event={'label':'PERFECT','delta':1,'lower_seconds':1.,'upper_seconds':1.017,
           'status':'excluded','reason':'possible_hold_or_dense_stack','detection_status':'candidate'}
    return {'notes':notes,'layout':{'receptor_y':.1,'lanes':[{'x':.2},{'x':.3}]},'analysis_width':200,
            'skin_detector':{'contract':{'held_body':FORMAT},'missing_template_roles':[]},
            'unsupported_intervals':[{'start_seconds':1.11,'end_seconds':1.12}],
            'matches':[],'deferred_matches':[],'combo_events':[],'judgment_events':[event],
            'coverage':{},'limitations':[],
            'hold_analysis':{'holds':[hold],'unresolved_tracks':[warning],'receptor_runs':[]},
            'visual_channels':{'note_types':{'notes':[{'note':0,'observations':[{
                'kind':'tap','role':'tap','reason':'image_cap_with_native_clearance',
                'playback_seconds':.9,'source_pts_seconds':10.9}]}]}}}


class DeferredWordTest(unittest.TestCase):
    def setUp(self):
        geometry=patch('piu_timeline.play.deferred_words.cap_extent_spacing',return_value=1.)
        geometry.start();self.addCleanup(geometry.stop)

    def test_early_word_retains_its_native_interval_and_future_hold_accounting(self):
        data=scenario();original=deepcopy(data)
        matches,indices=recover(data,data['notes'],[],{1,2})
        self.assertEqual(indices,[0]);match=matches[0]
        self.assertEqual((match['observation_lower_seconds'],match['observation_upper_seconds']),(1.,1.017))
        self.assertEqual(match['judgment_label'],'PERFECT');self.assertIsNone(match['combo_event'])
        self.assertEqual(match['recovery_method'],METHOD)
        self.assertEqual(match['hold_risk_accounting']['holds'],[0])
        self.assertEqual(data,original)

    def test_nullable_shared_clock_keeps_independent_measured_velocity(self):
        data=scenario();data['notes'][1]['motion_clock']=None
        self.assertEqual(recover(data,data['notes'],[],{1,2})[1],[0])

    def test_presentation_exposes_the_recovered_word_without_an_invented_onset(self):
        data=scenario();original=deepcopy(data);result=presentation(data)
        self.assertEqual(result['recovered_pre_hold_notes'],[0])
        self.assertEqual(result['coverage']['judgment_only_note_heads'],1)
        self.assertEqual(result['judgment_events'][0]['status'],'matched')
        self.assertNotIn('lane_onset_range',result['matches'][0])
        self.assertEqual(result['hold_analysis']['unresolved_tracks'],original['hold_analysis']['unresolved_tracks'])
        self.assertEqual(data,original)

    def test_supplied_display_correction_applies_to_risk_comparison_and_preserves_native_bounds(self):
        data=scenario();data['display_delay_correction_ms']=200
        data['judgment_events'][0].update(lower_seconds=1.18,upper_seconds=1.197)
        matches,indices=recover(data,data['notes'],[],{1,2})
        self.assertEqual(indices,[0]);match=matches[0]
        self.assertEqual(match['observation_lower_seconds'],1.18)
        self.assertEqual(match['observation_upper_seconds'],1.197)
        self.assertAlmostEqual(match['hold_risk_accounting']['risk_time_range'][0],.98)

    def test_uncertain_identity_risk_geometry_or_word_cannot_supply_input(self):
        for case in ('type','miss','detection','wide','old_profile','unknown_flag','overlap','censored','speed','hold_type'):
            with self.subTest(case=case):
                data=scenario();event=data['judgment_events'][0]
                if case=='type':data['notes'][0]['type_status']='unknown'
                elif case=='miss':event['label']='MISS'
                elif case=='detection':event['detection_status']='excluded'
                elif case=='wide':event['lower_seconds']=.8
                elif case=='old_profile':data['skin_detector']['contract']['held_body']={}
                elif case=='unknown_flag':data['unsupported_intervals'].append({'start_seconds':1.08,'end_seconds':1.09})
                elif case=='overlap':event.update(lower_seconds=1.13,upper_seconds=1.15)
                elif case=='censored':data['hold_analysis']['holds'][0]['start_censored']=True
                elif case=='speed':data['notes'][1].pop('velocity_pixels_per_second')
                else:data['notes'][0]['note_type']='hold'
                self.assertEqual(recover(data,data['notes'],[],{1,2})[1],[])

    def test_competing_refresh_or_unknown_row_remains_an_alternative(self):
        for case in ('refresh','row'):
            with self.subTest(case=case):
                data=scenario()
                if case=='refresh':data['judgment_events'].append({**data['judgment_events'][0],
                    'lower_seconds':1.017,'upper_seconds':1.034,'reason':'ambiguous_note_or_combo_association'})
                else:
                    data['judgment_events'][0].update(lower_seconds=1.019,upper_seconds=1.036)
                    data['notes'].append({**data['notes'][0],'lane':2,'target_seconds':1.045,'type_status':'unknown'})
                self.assertEqual(recover(data,data['notes'],[],{1,2})[1],[])

    def test_existing_word_or_counter_ownership_cannot_be_stolen(self):
        for source in ('combo','judgment'):
            with self.subTest(source=source):
                data=scenario();data['notes'].append({**data['notes'][0],'lane':2,'target_seconds':.97})
                match={'note':3,'target_seconds':.97,'combo_event':0 if source=='combo'else None,
                       'judgment_event':0 if source=='judgment'else None,
                       'observation_lower_seconds':1.,'observation_upper_seconds':1.02}
                matches,indices=recover(data,data['notes'],[match],{1,2})
                self.assertEqual(indices,[]);self.assertEqual(matches,[match])
