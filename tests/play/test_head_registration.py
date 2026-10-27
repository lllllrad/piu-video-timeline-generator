"""Registration uses visible cap geometry, never beat or input targets."""
import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from piu_timeline.play.head_registration import patch_offset,fit_offset,measure,project_coordinates,retain_measurements
from piu_timeline.play.screen_regions import visible_cap_bounds


def patch():
    channels=np.zeros((5,101,65),dtype=bool)
    color,white,visible,relaxed,valid=channels
    relaxed[32:66,15:50]=True
    white[35:65,17:48]=True;white[36:64,18:47]=False
    color[:]=relaxed&~white;visible[:]=relaxed|white;valid[:]=True
    return channels


class HeadRegistrationTest(unittest.TestCase):
    def test_sparse_qualified_images_keep_their_centers_without_inferring_missing_offsets(self):
        samples=[{'time':i*.02,'source_pts_seconds':i*.02+50,'detected_y_pixels':100-i,
                  'offset_pixels':1. if i%2 else .5}for i in range(7)]
        self.assertIsNone(fit_offset(samples))
        record=retain_measurements(samples)
        self.assertEqual(record['status'],'measured_only')
        raw=[[s['time'],s['detected_y_pixels']]for s in samples]+[[.15,90]]
        canonical=project_coordinates(raw,record)
        self.assertEqual(canonical[:-1],[[s['time'],s['detected_y_pixels']+s['offset_pixels']]for s in samples])
        self.assertEqual(canonical[-1],[.15,90])
        self.assertEqual(record['fallback_failure'],'insufficient_repeated_registration')
        expanded=samples+[{'time':.14,'source_pts_seconds':50.14,'detected_y_pixels':93,'offset_pixels':1.}]
        fitted=retain_measurements(expanded)
        self.assertEqual(fitted['status'],'registered')
        self.assertIsNone(fitted['fallback_failure'])

    def test_each_measured_frame_recovers_its_canonical_center_instead_of_a_median_shift(self):
        from piu_timeline.play.tracking import Track,fit_track
        times=[i*.02 for i in range(20)];offsets=[-.5,-1.5]*10
        actual=[[t,110-100*t]for t in times]
        raw=[[t,y-offset]for (t,y),offset in zip(actual,offsets,strict=True)]
        samples=[{'time':t,'source_pts_seconds':t+50,'detected_y_pixels':y,'offset_pixels':offset}
                 for (t,y),offset in zip(raw,offsets,strict=True)]
        record=fit_offset(samples);before=deepcopy((raw,record))
        self.assertEqual(record['status'],'registered')
        canonical=project_coordinates(raw,record)
        self.assertEqual(canonical,actual)
        self.assertEqual((raw,record),before)
        target=fit_track(Track(0,canonical),50,20)
        self.assertAlmostEqual(target['target_seconds'],.6)
        self.assertAlmostEqual(target['velocity_pixels_per_second'],-100)
        missing={**record,'observations':samples[:-1]}
        self.assertEqual(project_coordinates(raw,missing)[-1],[times[-1],raw[-1][1]+record['offset_pixels']])

    def test_unstable_global_offset_has_measured_positions_without_unverified_gap_corrections(self):
        samples=[{'time':i*.02,'source_pts_seconds':i*.02+50,'detected_y_pixels':100-i,
                  'offset_pixels':-1. if i<7 else 3.}for i in range(8)]
        record=fit_offset(samples);self.assertEqual(record['status'],'unresolved')
        raw=[[s['time'],s['detected_y_pixels']]for s in samples]+[[.2,90]]
        canonical=project_coordinates(raw,record)
        self.assertEqual(canonical[-2],[.14,96])
        self.assertEqual(canonical[-1],[.2,90])
        self.assertEqual(record['status'],'unresolved')

    def test_coordinate_measurements_cannot_change_native_identity_or_invent_frames(self):
        record={'status':'registered','offset_pixels':-1.,'observations':[
            {'time':1.,'detected_y_pixels':100.,'offset_pixels':-1.}]}
        for kind in ('position','frame','duplicate'):
            changed=deepcopy(record)
            if kind=='position':changed['observations'][0]['detected_y_pixels']=103
            elif kind=='frame':changed['observations'][0]['time']=2
            else:changed['observations']*=2
            with self.subTest(kind=kind),self.assertRaises(ValueError):project_coordinates([[1.,100.]],changed)

    def test_complete_cap_outside_hud_uses_measured_bounds_and_keeps_background_margin(self):
        data={'analysis_width':400,'analysis_height':400,'layout':{'receptor_y':.1,
              'lanes':[{'x':.3},{'x':.38},{'x':.5}],
              'combo_roi':[.25,.5,.1,.1],'judgment_roi':[.25,.35,.1,.1]}}
        box=[15,32,35,34]
        # The old center +/-0.8-spacing proxy overlaps the HUD here. The full
        # measured cap plus both five-pixel background margins does not.
        self.assertEqual(visible_cap_bounds(data,0,266,box,(101,65),34,5),[103,243,138,287])
        self.assertIsNone(visible_cap_bounds(data,0,261,box,(101,65),34,5))
        # Cap itself is clear at 261, but its required background is not.
        self.assertIsNotNone(visible_cap_bounds(data,0,261,box,(101,65),34))
        # The center is horizontally outside the HUD, but the cap edge is not.
        self.assertIsNone(visible_cap_bounds(data,1,220,box,(101,65),34,5))
        self.assertIsNotNone(visible_cap_bounds(data,2,220,box,(101,65),34,5))

    def test_footprint_must_stay_inside_field_and_outside_receptor_effect_band(self):
        data={'analysis_width':400,'analysis_height':400,
              'layout':{'receptor_y':.1,'lanes':[{'x':.3},{'x':.01}]}}
        for y,clear in ((359,True),(360,False),(74,True),(73,False)):
            self.assertEqual(visible_cap_bounds(data,0,y,[15,32,35,34],(101,65),34,5)is not None,clear)
        self.assertIsNone(visible_cap_bounds(data,1,150,[15,32,35,34],(101,65),34,5))

    def test_visible_cap_near_hud_supplies_native_registration_without_hidden_pixels(self):
        with tempfile.TemporaryDirectory()as tmp:
            path=Path(tmp)/'pixels.npz';times=np.arange(10)*.02+10
            for y,expected in ((266,True),(261,False)):
                np.savez_compressed(path,masks=np.array([np.packbits(patch(),axis=-1)]*10),
                                    times=times,pts=times+30,lanes=np.zeros(10,dtype=int),
                                    ys=np.full(10,y),spacing=34,columns=65)
                data={'analysis_width':400,'analysis_height':400,
                      'layout':{'receptor_y':.1,'lanes':[{'x':.3}],
                                'combo_roi':[.25,.5,.1,.1],'judgment_roi':[.25,.35,.1,.1]},
                      'notes':[{'lane':0,'points':[[float(t),y]for t in times]}]}
                result=measure(data,path)
                self.assertEqual(bool(result['notes']),expected)
                if expected:
                    fitted=result['notes'][0]
                    self.assertEqual(fitted['offset_pixels'],-1)
                    self.assertEqual(len(fitted['observations']),10)
                    self.assertEqual(fitted['observations'][0]['support_bounds_pixels'],[103,243,138,287])

    def test_fractional_detection_center_is_not_the_rounded_patch_center(self):
        with tempfile.TemporaryDirectory()as tmp:
            path=Path(tmp)/'pixels.npz';times=np.arange(10)*.02+10
            for y,expected in ((150.5,-1.5),(151.5,-.5)):
                np.savez_compressed(path,masks=np.array([np.packbits(patch(),axis=-1)]*10),
                                    times=times,pts=times+30,lanes=np.zeros(10,dtype=int),
                                    ys=np.full(10,y),spacing=34,columns=65)
                data={'analysis_width':400,'analysis_height':400,'layout':{'receptor_y':.1,'lanes':[{'x':.3}]},
                      'notes':[{'lane':0,'points':[[float(t),y]for t in times]}]}
                fitted=measure(data,path)['notes'][0]
                self.assertEqual(fitted['offset_pixels'],expected)
                self.assertEqual(y+expected,round(y)-1)

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

    def test_normalized_coordinate_roundoff_preserves_exact_pixel_boundary(self):
        samples=[{'time':i*.02,'offset_pixels':-1.}for i in range(20)]
        # Pixel coordinates reconstructed from normalized positions are not
        # necessarily exactly representable, including at half-pixel centers.
        samples[-1]['offset_pixels']=205.5-(207.5/400)*400
        samples[-2]['offset_pixels']=1.
        original=deepcopy(samples)
        fitted=fit_offset(samples)
        self.assertEqual(fitted['status'],'registered')
        self.assertEqual(fitted['conflicting_observations'],samples[-2:-1])
        self.assertEqual(samples,original)
        samples[-1]['offset_pixels']=-2.001
        self.assertEqual(fit_offset(samples)['status'],'unresolved')
        self.assertEqual(fit_offset(samples)['conflicting_observations'],samples[-2:])

    def test_pixels_join_raw_detection_positions_even_after_a_previous_projection(self):
        with tempfile.TemporaryDirectory()as tmp:
            path=Path(tmp)/'pixels.npz';times=np.arange(10)*.02+10
            np.savez_compressed(path,masks=np.array([np.packbits(patch(),axis=-1)]*10),
                                times=times,pts=times+30,lanes=np.zeros(10,dtype=int),
                                ys=np.full(10,150),spacing=34,columns=65)
            data={'analysis_width':400,'analysis_height':400,'layout':{'receptor_y':.1,'lanes':[{'x':.3}]},
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
