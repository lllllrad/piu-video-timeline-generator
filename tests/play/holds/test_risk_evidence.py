"""Native body proximity needs exact ownership and a registered approaching cap."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from piu_timeline.play.holds.risk_evidence import derive
from piu_timeline.play.holds.risk_cache import context,prepare
from piu_timeline.play.holds.risk_ownership import account_interval
from piu_timeline.play.deferred_words import recover
from piu_timeline.play.skins.held import FORMAT as HELD_FORMAT
from piu_timeline.play.skins.anchors import FORMAT as ANCHOR_FORMAT
from piu_timeline.play.skins.bank import load_bank
from tests.play.skins.test_detector import examples


def scenario(root):
    examples(root);bank=load_bank(root/'bank.json')
    bank['anchor_registrations']={'tap':{}}
    layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]}
    point={'time':1.,'source_pts':11.,'covered_bounds_pixels':[26,54],
           'body_template_support':True,'image_node':0,'head_y':48.,'trace':'frames.jsonl',
           'motion_link':{'method':'registered_frame_displacement','displacement_pixels':8.,'source_pts_range':[10.983,11.]}}
    hold={'id':0,'lane':0,'head_note':0,'tail_note':1,'start_censored':False,'end_censored':False,
          'start_range':[1.1,1.12],'end_range':[1.4,1.42],'body_frames':8,
          'body_evidence':'skin_temporal_image_regions','image_connection_evidence':[point]}
    sample={'time':1.,'source_pts_seconds':11.,'native_y_pixels':48.,
            'native_cap_reference_template':'tap','native_cap_coordinate_uncertainty_pixels':1.,
            'native_cap_reference_scale_y':1.}
    data={'media':{'size':123},'game_roi':[0,0,200,300],'frame_count':1,'start_seconds':.5,'end_seconds':2.,
          'layout':layout,'analysis_width':200,'analysis_height':300,
          'skin_detector':{'bank_path':str(root/'bank.json'),'contract':{'bank':bank['contract']}},
          'head_registration':{'format':{'native_cap_registration':ANCHOR_FORMAT},
                               'notes':[{'note':0,'observations':[sample]}]},
          'hold_analysis':{'holds':[hold]},
          'unsupported_intervals':[{'start_seconds':1.,'end_seconds':1.}]}
    frame={'playback_seconds':1.,'source_pts_seconds':11.,'possible_hold_or_dense_stack':True,
           'skin_observations':[{'lane':0,'role':'hold_body','template':'hold_body',
              'classification_status':'full_pattern','bounds_pixels':[16,top,24,top+12],
              'alternatives':[]}for top in(26,34,42)]}
    return data,[frame],bank


class NativeBodyRiskTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.data,self.native,self.bank=scenario(self.root)

    def test_same_component_below_receptor_is_approach_not_a_held_state(self):
        result=derive(self.data,self.native,self.bank)
        cause=result['frames'][0]['causes'][0]
        self.assertEqual(cause['owner_hold'],0);self.assertEqual(cause['state'],'approaching')
        self.assertEqual(cause['vertical_range_pixels'],[26,54])
        self.assertEqual(cause['ownership']['minimum_head_top_pixels'],27.)
        self.assertEqual(result['counts'],{'approaching':1})

    def test_missing_conflicting_or_different_frame_geometry_remains_unresolved(self):
        for case in ('missing','ambiguous','pts','bounds','registration','uncertainty','motion','method','at_receptor'):
            with self.subTest(case=case):
                data=deepcopy(self.data);hold=data['hold_analysis']['holds'][0]
                point=hold['image_connection_evidence'][0]
                sample=data['head_registration']['notes'][0]['observations'][0]
                if case=='missing':hold['image_connection_evidence']=[]
                elif case=='ambiguous':data['hold_analysis']['holds'].append({**deepcopy(hold),'id':1})
                elif case=='pts':point['source_pts']=12.
                elif case=='bounds':point['covered_bounds_pixels']=[27,54]
                elif case=='registration':sample['native_cap_reference_template']='unregistered'
                elif case=='uncertainty':sample['native_cap_coordinate_uncertainty_pixels']=.1
                elif case=='motion':point['motion_link']['displacement_pixels']=0
                elif case=='method':point['motion_link']['method']='unregistered_fit'
                else:sample['native_y_pixels']=point['head_y']=35.
                cause=derive(data,self.native,self.bank)['frames'][0]['causes'][0]
                self.assertEqual(cause['state'],'unresolved')

    def test_unowned_second_lane_is_retained_even_with_known_approach(self):
        native=deepcopy(self.native)
        native[0]['skin_observations'] += [{**p,'lane':1}for p in self.native[0]['skin_observations']]
        result=derive(self.data,native,self.bank)
        self.assertEqual([c['state']for c in result['frames'][0]['causes']],['approaching','unresolved'])

    def test_native_flag_interval_or_pts_disagreement_fails_explicitly(self):
        for case in ('flag','interval','pts','bank'):
            with self.subTest(case=case):
                data,native,bank=deepcopy((self.data,self.native,self.bank))
                if case=='flag':native[0]['possible_hold_or_dense_stack']=False
                elif case=='interval':data['unsupported_intervals'][0]['end_seconds']=1.017
                elif case=='pts':native.append(deepcopy(native[0]))
                else:bank['contract']={}
                with self.assertRaises(ValueError):derive(data,native,bank)

    def test_later_owned_body_can_reach_receptor_after_initial_registered_approach(self):
        data,native=deepcopy((self.data,self.native))
        later=deepcopy(native[0]);later.update(playback_seconds=1.017,source_pts_seconds=11.017)
        native.append(later);data['frame_count']=2
        data['unsupported_intervals'][0]['end_seconds']=1.017
        hold=data['hold_analysis']['holds'][0];point=deepcopy(hold['image_connection_evidence'][0])
        point.update(time=1.017,source_pts=11.017,head_y=35.,image_node=1,
                     motion_link={'method':'registered_frame_displacement','displacement_pixels':13.,'source_pts_range':[11.,11.017]})
        hold['image_connection_evidence'].append(point)
        observations=data['head_registration']['notes'][0]['observations']
        observations.append({**observations[0],'time':1.017,'source_pts_seconds':11.017,'native_y_pixels':35.})
        result=derive(data,native,self.bank);result['contract']=context(data);data['body_risk_evidence']=result
        self.assertEqual([f['causes'][0]['state']for f in result['frames']],['approaching','unresolved'])
        interval=data['unsupported_intervals'][0];guards=[(hold,.04)]
        self.assertIsNotNone(account_interval(data,interval,guards,.95))
        result['frames'][0]['causes'].append({**result['frames'][0]['causes'][0],'state':'unresolved'})
        self.assertIsNone(account_interval(data,interval,guards,.95))

    def test_only_whole_source_bound_owned_intervals_can_waive_proximity(self):
        result=derive(self.data,self.native,self.bank);result['contract']=context(self.data)
        data={**self.data,'body_risk_evidence':result};interval=data['unsupported_intervals'][0]
        guards=[(data['hold_analysis']['holds'][0],.04)]
        self.assertEqual(account_interval(data,interval,guards,.95)['holds'],[0])
        for case in ('media','geometry','registration','interval','unknown_cause','first_unresolved','word_overlap'):
            with self.subTest(case=case):
                changed=deepcopy(data);hi=.95
                if case=='media':changed['media']['size']+=1
                elif case=='geometry':changed['hold_analysis']['holds'][0]['body_frames']+=1
                elif case=='registration':changed['head_registration']['notes']=[]
                elif case=='interval':changed['unsupported_intervals'][0]['end_seconds']+=.017
                elif case=='unknown_cause':changed['body_risk_evidence']['frames'][0]['causes'].append({'state':'unresolved'})
                elif case=='first_unresolved':changed['body_risk_evidence']['frames'][0]['causes'][0]['state']='unresolved'
                else:hi=1.08
                self.assertIsNone(account_interval(changed,changed['unsupported_intervals'][0],guards,hi))

    def test_cache_reuses_native_derivation_and_rejects_changed_source(self):
        (self.root/'frames.jsonl').write_text(json.dumps(self.native[0])+'\n')
        # No cap registration certificate in this synthetic bank: ownership is
        # retained, but it cannot positively establish an approaching cap.
        first=prepare(self.data,self.root)['body_risk_evidence']
        self.assertEqual(first['status'],'available')
        artifact=self.root/'body-risk-evidence.json';timestamp=artifact.stat().st_mtime_ns
        self.assertEqual(prepare(self.data,self.root)['body_risk_evidence'],first)
        self.assertEqual(artifact.stat().st_mtime_ns,timestamp)
        changed=deepcopy(self.data);changed['media']['size']+=1
        self.assertNotEqual(prepare(changed,self.root)['body_risk_evidence']['contract'],first['contract'])
        (self.root/'frames.jsonl').unlink()
        failed=prepare(self.data,self.root)['body_risk_evidence']
        self.assertEqual(failed['status'],'failed');self.assertEqual(failed['frames'],[])
        self.assertEqual(failed['warnings'][0]['reason'],'native_body_risk_evidence_unavailable')

    def test_geometric_approach_recovers_native_word_but_unknown_cause_keeps_veto(self):
        data=self.data
        data['skin_detector']['contract']['held_body']=HELD_FORMAT
        data['skin_detector']['missing_template_roles']=[]
        data['notes']=[{'lane':0,'status':'estimated','target_seconds':t,
                        'velocity_pixels_per_second':-500}for t in(1.11,1.41)]
        data['notes'].append({'lane':1,'status':'estimated','type_status':'tap','target_seconds':.96,
                              'prediction_uncertainty_seconds':.005})
        data.update(matches=[],combo_events=[],judgment_events=[{'label':'PERFECT','delta':1,
            'lower_seconds':.95,'upper_seconds':.967,'status':'excluded',
            'reason':'possible_hold_or_dense_stack','detection_status':'candidate'}])
        result=derive(data,self.native,self.bank);result['contract']=context(data)
        data['body_risk_evidence']=result;original=deepcopy(data)
        matches,indices=recover(data,data['notes'],[],{0,1})
        self.assertEqual(indices,[2])
        self.assertEqual([matches[0][k]for k in('observation_lower_seconds','observation_upper_seconds')],[.95,.967])
        self.assertEqual(data,original)
        result['frames'][0]['causes'].append({'state':'unresolved'})
        self.assertEqual(recover(data,data['notes'],[],{0,1})[1],[])
