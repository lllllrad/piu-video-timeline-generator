"""A noisy time-to-distance conversion is distinct from native pixel precision."""
from copy import deepcopy
import unittest

from piu_timeline.play.spacing_checks import spacing_failures
from piu_timeline.play.beats.coordinates import prepare
from tests.play.beats.test_coordinates import fixture


def clock_pair():
    times=[.4+i/60 for i in range(8)]
    clock={'origin':0.,'velocity':480.,'intercept':0.,'residual':3.,'window':[0.,.5]}
    notes=[{'lane':i,'status':'estimated','target_seconds':1.+.1*i,
            'points':[(t,200+50*i-480*(t-.4))for t in times],
            'motion_clock':clock,'motion_target_phase':480.+50*i}for i in range(2)]
    motion={'samples':[{'time':t,'chunk':0}for t in times],
            'coordinate_registration':{'chunks':[{'chunk':0,'status':'fitted','head_offsets':[
                {'note':i,'offset_pixels':200.+50*i}for i in range(2)]}]}}
    return notes,motion


class ClockConversionTest(unittest.TestCase):
    def test_short_beat_correction_respects_the_measured_clock_slope_error(self):
        notes,motion=clock_pair();original=deepcopy((notes,motion));checks=[]
        self.assertEqual(spacing_failures(notes,40,motion,diagnostics=checks),[])
        conversion=checks[0]['clock_conversion']
        self.assertAlmostEqual(conversion['velocity_error_pixels_per_second'],18.)
        self.assertAlmostEqual(conversion['position_error_pixels'],1.8)
        self.assertEqual((notes,motion),original)

    def test_exact_clock_and_rows_outside_the_clock_bound_still_fail(self):
        for case in ('exact_clock','wrong_row'):
            notes,motion=clock_pair()
            if case=='exact_clock':notes[0]['motion_clock']['residual']=0.
            else:notes[1]['target_seconds']+=.04
            failures=spacing_failures(notes,40,motion)
            self.assertEqual({w['note']for w in failures},{0,1},case)
            self.assertEqual(failures[0]['tolerance_pixels'],1.)

    def test_independent_native_models_keep_their_original_pixel_gate(self):
        data=fixture()
        for note in data['notes']:
            note['motion_clock']={'origin':0.,'velocity':240.,'intercept':0.,'residual':100.,'window':[0.,1.]}
        support=prepare(data,40);data['notes'][4]['target_seconds']+=.06
        failures=spacing_failures(data['notes'],40,data['scroll_motion'],support)
        pair=next(w for w in failures if w['peer_notes']==[4,5])
        self.assertEqual(pair['tolerance_pixels'],1.)
        self.assertNotIn('clock_conversion',pair)
        self.assertEqual({w['note']for w in failures},{4})
