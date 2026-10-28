"""Independent native geometry can validate beat spacing despite clock bias."""
from copy import deepcopy
import unittest

from piu_timeline.play.beats.coordinates import prepare,predictions,fit
from piu_timeline.play.spacing_checks import spacing_failures


def fixture():
    times=[.5+i*.02 for i in range(10)]
    notes=[{'lane':i%3,'status':'estimated','target_seconds':1+i*.125,
            'points':[(t,40+240*(1+i*.125-t))for t in times],
            'motion_clock':{'origin':0,'velocity':244 if i==4 else 240,'intercept':0},
            'motion_target_phase':240*(1+i*.125)}for i in range(9)]
    return {'analysis_height':600,'layout':{'receptor_y':40/600},'notes':notes,
            'head_registration':{'notes':[{'note':i,'status':'registered',
                'observations':[{'time':t}for t in times]}for i in range(9)]},
            'scroll_motion':{'samples':[{'time':t,'source_pts':80+t,'phase':240*t,'chunk':0}for t in times],
                'coordinate_registration':{'chunks':[{'chunk':0,'status':'fitted','head_offsets':[
                    {'note':i,'offset_pixels':40+240*(1+i*.125)}for i in range(9)]}]}}}


class BeatCoordinateTest(unittest.TestCase):
    def test_measured_native_centers_do_not_need_a_constant_outline_offset(self):
        data=fixture()
        for record in data['head_registration']['notes']:
            record.update(status='unresolved',coordinate_method='native_cap_measurements')
        support=prepare(data,40)
        self.assertEqual(spacing_failures(data['notes'],40,data['scroll_motion'],support),[])
        # Real positional disagreement still invalidates the measured anchor.
        t,y=data['notes'][4]['points'][0];data['notes'][4]['points'][0]=(t,y+3)
        self.assertEqual(predictions(4,5,data['notes'],(.5,.68),prepare(data,40)),[])

    def test_independent_heads_validate_pixel_spacing_despite_local_clock_bias(self):
        data=fixture();original=deepcopy(data);motion=data['scroll_motion'];notes=data['notes']
        old=spacing_failures(notes,40,motion)
        self.assertTrue(any(w['peer_notes']==[4,5]for w in old))
        support=prepare(data,40);frozen=deepcopy(support);checks=[]
        self.assertEqual(spacing_failures(notes,40,motion,support,checks),[])
        proof=next(c for c in checks if c['peer_notes']==[4,5])['models'][0]
        self.assertAlmostEqual(proof['predicted_gap_pixels'],30)
        self.assertAlmostEqual(proof['velocity_pixels_per_second'],240)
        self.assertEqual({r['note']for r in proof['references']},{0,1,2,3,6,7,8})
        self.assertEqual(proof['references'][0]['source_pts_range'],[80.5,80.68])
        self.assertEqual((data,support),(original,frozen))

    def test_wrong_row_is_rejected_by_the_independent_model(self):
        data=fixture();support=prepare(data,40);data['notes'][4]['target_seconds']+=.06
        failures=spacing_failures(data['notes'],40,data['scroll_motion'],support)
        pair=next(w for w in failures if w['peer_notes']==[4,5])
        self.assertIn('independent_coordinate_models',pair)
        self.assertGreater(abs(pair['observed_gap_pixels']-pair['reconstructed_gap_pixels']),pair['tolerance_pixels'])

    def test_native_outlier_unverified_cap_and_short_support_cannot_supply_an_anchor(self):
        for kind in ('outlier','unverified','short','failed_block'):
            data=fixture()
            if kind=='outlier':
                t,y=data['notes'][4]['points'][0];data['notes'][4]['points'][0]=(t,y+3)
            if kind=='unverified':data['head_registration']['notes'][4]['status']='unresolved'
            if kind=='short':data['head_registration']['notes'][4]['observations']=data['head_registration']['notes'][4]['observations'][:3]
            if kind=='failed_block':data['scroll_motion']['coordinate_registration']['chunks'][0]['status']='failed'
            self.assertEqual(predictions(4,5,data['notes'],(.5,.68),prepare(data,40)),[],kind)

    def test_no_extrapolation_or_self_training_from_the_tested_pair(self):
        data=fixture();support=prepare(data,40)
        self.assertEqual(predictions(0,1,data['notes'],(.5,.68),support),[])
        self.assertEqual(predictions(4,5,data['notes'],(.51,.55),support),[])
        support['chunks'][0]={i:v for i,v in support['chunks'][0].items()if i in (0,2,4,5,6,8)}
        # Six heads including the pair leave only four independent references.
        self.assertEqual(predictions(4,5,data['notes'],(.5,.68),support),[])

    def test_all_reference_residuals_must_fit_without_discarding_a_speed_transition(self):
        data=fixture();support=prepare(data,40)
        refs=[{'note':i,'target_seconds':data['notes'][i]['target_seconds'],**head}
              for i,head in support['chunks'][0].items()if i not in (4,5)]
        self.assertIsNotNone(fit(refs,40))
        for kind in ('bad_row','speed_change','one_lane','one_time'):
            changed=deepcopy(refs)
            if kind=='bad_row':changed[2]['target_seconds']+=.08
            if kind=='speed_change':
                for r in changed:r['offset']+=max(0,r['target_seconds']-1.4)*60
            if kind=='one_lane':
                for r in changed:r['lane']=0
            if kind=='one_time':
                for r in changed:r['target_seconds']=1
            self.assertIsNone(fit(changed,40),kind)

    def test_conflicting_source_coordinates_cannot_count_as_native_pair_support(self):
        data=fixture();record=data['head_registration']['notes'][4]
        record['observations'][0]['native_cap_registration_status']='conflicting'
        support=prepare(data,40)
        models=predictions(4,5,data['notes'],(.5,.68),support)
        self.assertTrue(models)
        self.assertTrue(all(model['coobserved_points']==9 for model in models))
        for sample in record['observations']:sample['native_cap_registration_status']='conflicting'
        self.assertEqual(predictions(4,5,data['notes'],(.5,.68),prepare(data,40)),[])
