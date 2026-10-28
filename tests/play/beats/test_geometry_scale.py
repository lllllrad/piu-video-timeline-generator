"""Stored native observations preserve decisions when game geometry is resized."""
from copy import deepcopy
import json
import unittest

from piu_timeline.play.beats.coordinates import prepare,predictions
from piu_timeline.play.beats.chords import prepare as prepare_chords
from piu_timeline.play.spacing_checks import spacing_failures
from tests.play.beats.test_coordinates import fixture
from tests.play.beats.test_chords import fixture as chord_fixture


def resized(data,scale):
    data=deepcopy(data)
    for key in ('analysis_width','analysis_height'):
        if key in data:data[key]*=scale
    for note in data['notes']:
        note['points']=[(t,y*scale)for t,y in note['points']]
        if 'motion_clock'in note:
            for key in ('velocity','intercept'):note['motion_clock'][key]*=scale
        if 'motion_target_phase'in note:note['motion_target_phase']*=scale
    for record in data['head_registration']['notes']:
        if 'coordinate_uncertainty_pixels'in record:record['coordinate_uncertainty_pixels']*=scale
    motion=data.get('scroll_motion',{})
    for sample in motion.get('samples',[]):sample['phase']*=scale
    for chunk in motion.get('coordinate_registration',{}).get('chunks',[]):
        for head in chunk['head_offsets']:head['offset_pixels']*=scale
    # This is the stored analysis representation, rather than an internal
    # coordinate map with integer dictionary keys.
    return json.loads(json.dumps(data))


class GeometryScaleTest(unittest.TestCase):
    def test_native_measurement_budget_is_relative_to_lane_spacing(self):
        for error,accepted in ((1.2,True),(1.8,False)):
            data=fixture();t,y=data['notes'][4]['points'][0];data['notes'][4]['points'][0]=(t,y+error)
            for scale in (.5,1.,2.,4.):
                with self.subTest(error=error,scale=scale):
                    support=prepare(resized(data,scale),40*scale)
                    self.assertEqual(4 in support['chunks'][0],accepted)

    def test_independent_reference_fit_has_the_same_verdict_after_storage_and_resize(self):
        for error,accepted in ((.8,True),(1.2,True),(2.4,False)):
            data=fixture();data['notes'][0]['points']=[(t,y+error)for t,y in data['notes'][0]['points']]
            data['scroll_motion']['coordinate_registration']['chunks'][0]['head_offsets'][0]['offset_pixels']+=error
            for scale in (.5,1.,2.,4.):
                d=resized(data,scale);support=prepare(d,40*scale)
                with self.subTest(error=error,scale=scale):
                    self.assertEqual(bool(predictions(4,5,d['notes'],(.5,.68),support)),accepted)

    def test_spacing_conflicts_remain_conflicts_at_every_size(self):
        for wrong in (False,True):
            data=fixture()
            if wrong:data['notes'][4]['target_seconds']+=.012
            for scale in (.5,1.,2.,4.):
                d=resized(data,scale);support=prepare(d,40*scale)
                warnings=spacing_failures(d['notes'],40*scale,d['scroll_motion'],support)
                with self.subTest(wrong=wrong,scale=scale):
                    self.assertEqual(4 in {w['note']for w in warnings},wrong)

    def test_concurrent_native_heads_remain_concurrent_at_every_size(self):
        data=chord_fixture()
        for point in data['notes'][1]['points']:point[1]+=.6
        for scale in (.5,1.,2.,4.):
            proofs=prepare_chords(resized(data,scale),40*scale)
            with self.subTest(scale=scale):self.assertEqual([p['peer_notes']for p in proofs],[[0,1]])
