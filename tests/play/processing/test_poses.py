"""Animation is observed presence; absence must reject all supported native shapes."""
from pathlib import Path
import tempfile
import unittest

import numpy as np

from piu_timeline.play.processing import observe_processing
from piu_timeline.play.processing.poses import references,compare
from tests.play.processing.fixtures import fixture


class ProcessingPoseTest(unittest.TestCase):
    def test_only_repeated_moving_shapes_supply_additional_references(self):
        a=np.zeros((15,15),dtype=bool);a[:,2:5]=True
        b=np.zeros_like(a);b[10:13,:]=True
        values=[(10+i,30+10*i,a if i%2==0 else b)for i in range(6)]
        poses=references(values,20)
        self.assertEqual(len(poses),2)
        self.assertTrue(all(len(p['evidence']['supporting_source_pts_seconds'])==3 for p in poses))
        self.assertEqual(references([(p,30,m)for p,_,m in values],20),[])
        self.assertEqual(references([(10,y,m)for _,y,m in values],20),[])
        self.assertEqual(references(values[:4],20),[])

    def test_one_present_pose_vetoes_absence_of_other_poses(self):
        a=np.zeros((15,15),dtype=bool);a[:,2:5]=True
        b=np.zeros_like(a);b[10:13,:]=True
        reference={'mask':a,'poses':[{'mask':b}]};light=np.zeros((40,15),dtype=bool)
        color=np.zeros_like(light);color[13:28]=b
        event=compare(color,light,reference,20,7,20)
        self.assertEqual(event['state'],'present');self.assertEqual(event['template_pose'],0)
        self.assertEqual(compare(np.zeros_like(color),light,reference,20,7,20)['state'],'absent')
        # Most of one shape is outside the image: the other shape's clear
        # absence cannot turn this into a complete absence observation.
        clipped={'mask':a,'poses':[{'mask':np.roll(b,-10,axis=0)}]}
        self.assertEqual(compare(np.zeros_like(color),light,clipped,5,7,20)['state'],'unknown')
        self.assertEqual(compare(color,np.ones_like(light),reference,20,7,20)['unknown_reason'],'white_effect')

    def test_animated_native_capture_retains_real_disappearance_and_original_pts(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);data,_,_=fixture(root,animated=True)
            event=observe_processing(data,root/'processing-features.npz')['notes'][0]
            self.assertEqual(event['status'],'disappeared_near_receptor')
            self.assertEqual(event['source_pts_seconds'],[42+59/60,43.])
            self.assertGreaterEqual(len(event['template_evidence']['poses']),3)
            before=[s for s in event['samples']if .92<s['time']<1.]
            self.assertGreaterEqual(len(before),3)
            self.assertTrue(all(s['state']=='present'for s in before))
            self.assertEqual((root/'source.mkv').read_bytes(),b'unchanged recording')

    def test_clear_legacy_band_uses_the_same_animation_model(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);data,_,_=fixture(root,animated=True,hud=False)
            (root/'native-features/manifest.json').unlink()
            event=observe_processing(data,root/'processing-features.npz')['notes'][0]
            self.assertEqual(event['status'],'disappeared_near_receptor')
            self.assertEqual(event['source_pts_seconds'],[42+59/60,43.])
            self.assertEqual(event['template_evidence']['trace'],'processing-features.npz')
            self.assertGreaterEqual(len(event['template_evidence']['poses']),3)
