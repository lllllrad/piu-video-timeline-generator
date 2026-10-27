"""A short raster subset cannot override independently validated native offsets."""
from copy import deepcopy
import unittest

from piu_timeline.play.beats.coordinates import prepare
from piu_timeline.play.spacing_checks import spacing_failures
from tests.play.beats.test_coordinates import fixture


def biased_adjacency():
    data=fixture()
    for index,direction in ((4,1),(5,-1)):
        data['notes'][index]['points']=[(t,y+direction*(.6 if j<6 else -.9))
                                      for j,(t,y)in enumerate(data['notes'][index]['points'])]
    # Another cap intervenes only in later frames. Full native observations
    # still locate the two tested heads; their means have zero raster bias.
    data['notes'].append({'lane':3,'status':'estimated','target_seconds':1.5625,
                         'points':[(t,40+240*(1.5625-t))for t,_ in data['notes'][4]['points'][6:]]})
    return data


class RegisteredSpacingTest(unittest.TestCase):
    def test_independent_model_compares_fitted_offsets_with_original_pixel_limit(self):
        data=biased_adjacency();original=deepcopy(data);support=prepare(data,40);checks=[]
        self.assertEqual(spacing_failures(data['notes'],40,data['scroll_motion'],support,checks),[])
        pair=next(c for c in checks if c['peer_notes']==[4,5])
        self.assertAlmostEqual(pair['observed_gap_pixels'],28.8)
        self.assertAlmostEqual(pair['comparison_gap_pixels'],30.)
        self.assertEqual(pair['comparison_basis'],'independent_registered_offsets')
        self.assertEqual(data,original)

    def test_wrong_row_or_unverified_native_offsets_cannot_pass(self):
        for case in ('wrong_row','invalid_native'):
            data=biased_adjacency()
            if case=='wrong_row':data['notes'][4]['target_seconds']+=.06
            else:
                t,y=data['notes'][4]['points'][0];data['notes'][4]['points'][0]=(t,y+3)
            support=prepare(data,40)
            failures=spacing_failures(data['notes'],40,data['scroll_motion'],support)
            pair=next(w for w in failures if w['peer_notes']==[4,5])
            self.assertEqual(pair['tolerance_pixels'],1.)
            if case=='wrong_row':
                self.assertGreater(abs(pair['reconstructed_gap_pixels']-pair['comparison_gap_pixels']),1.)
            else:self.assertNotIn('comparison_basis',pair)
