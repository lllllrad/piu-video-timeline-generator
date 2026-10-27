"""Registration uses visible cap geometry, never beat or input targets."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from piu_timeline.play.head_registration import patch_offset,fit_offset,measure


def patch():
    channels=np.zeros((5,101,65),dtype=bool)
    color,white,visible,relaxed,valid=channels
    relaxed[32:66,15:50]=True
    white[35:65,17:48]=True;white[36:64,18:47]=False
    color[:]=relaxed&~white;visible[:]=relaxed|white;valid[:]=True
    return channels


class HeadRegistrationTest(unittest.TestCase):
    def test_isolated_crossing_retains_calibration_position_uncertainty(self):
        from piu_timeline.play.tracking import Track,fit_track
        track=Track(0,[[i*.01,80-i]for i in range(20)])
        baseline=fit_track(track,50,20)
        track.registration_uncertainty_pixels=1
        registered=fit_track(track,50,20)
        self.assertEqual(registered['status'],'estimated')
        self.assertAlmostEqual(registered['target_seconds'],baseline['target_seconds'])
        self.assertGreater(registered['prediction_uncertainty_seconds'],baseline['prediction_uncertainty_seconds'])
        self.assertAlmostEqual(registered['prediction_uncertainty_seconds'],.01)

    def test_outer_silhouette_defines_anchor_instead_of_inner_outline(self):
        masks=patch()
        offset,bounds=patch_offset(np.packbits(masks,axis=-1),65,34)
        self.assertEqual(offset,-1.)
        self.assertEqual(bounds,[15,32,35,34])
        masks[3,:32,20:45]=True;masks[0,:32,20:45]=True
        self.assertIsNone(patch_offset(np.packbits(masks,axis=-1),65,34))

    def test_clipped_caps_cannot_supply_registration(self):
        masks=patch();masks[4,32:34]=False
        self.assertIsNone(patch_offset(np.packbits(masks,axis=-1),65,34))

    def test_repeated_consistent_offsets_required_and_conflicts_retained(self):
        samples=[{'time':i*.02,'source_pts_seconds':i*.02+50,'offset_pixels':-1.}for i in range(20)]
        self.assertIsNone(fit_offset(samples[:7]))
        compressed=[{**s,'time':i*.001}for i,s in enumerate(samples)]
        self.assertIsNone(fit_offset(compressed))
        self.assertEqual(fit_offset(samples)['status'],'registered')
        samples[-1]['offset_pixels']=1
        fitted=fit_offset(samples)
        self.assertEqual(fitted['status'],'registered')
        self.assertEqual(fitted['conflicting_observations'],samples[-1:])
        for s in samples[::2]:s['offset_pixels']=1
        self.assertEqual(fit_offset(samples)['status'],'unresolved')

    def test_pixels_join_raw_detection_positions_even_after_a_previous_projection(self):
        with tempfile.TemporaryDirectory()as tmp:
            path=Path(tmp)/'pixels.npz';times=np.arange(10)*.02+10
            np.savez_compressed(path,masks=np.array([np.packbits(patch(),axis=-1)]*10),
                                times=times,pts=times+30,lanes=np.zeros(10,dtype=int),
                                ys=np.full(10,150),spacing=34,columns=65)
            data={'analysis_height':400,'layout':{'receptor_y':.1,'lanes':[{'x':.3}]},
                  'notes':[{'lane':0,'points':[[float(t),149]for t in times],
                            'detected_points':[[float(t),150]for t in times],
                            'target_seconds':999,'judgment':'MISS'}]}
            result=measure(data,path)
            self.assertEqual(result['notes'][0]['offset_pixels'],-1)
            self.assertEqual(len(result['notes'][0]['observations']),10)
            self.assertEqual(result['notes'][0]['observations'][0]['source_pts_seconds'],40)
            self.assertEqual(result['warnings'],[])
            # The method cannot obtain the same result from a different raw identity.
            data['notes'][0].pop('detected_points')
            self.assertEqual(measure(data,path)['notes'],[])
            json.dumps(result,allow_nan=False)
