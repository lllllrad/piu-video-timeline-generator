"""Persistence learns clear same-head pixels, never a HUD-covered silhouette."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from piu_timeline.play.processing import observe_processing
from piu_timeline.play.processing.templates import learn,hud_regions
from tests.play.processing.fixtures import fixture




class ProcessingTemplateTest(unittest.TestCase):
    def test_full_approach_supplies_clear_reference_when_band_is_inside_known_hud(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);data,times,pts=fixture(root);original=deepcopy(data)
            reference=learn(data,root,times,pts)[0]
            self.assertGreaterEqual(reference['evidence']['frames'],3)
            points={round(t+42,6):y for t,y in data['notes'][0]['points']}
            for p in reference['evidence']['source_pts_seconds']:
                self.assertEqual(hud_regions(data['layout'],2,points[round(p,6)],15,325,200),[])
            event=observe_processing(data,root/'processing-features.npz')['notes'][0]
            self.assertEqual(event['status'],'disappeared_near_receptor')
            self.assertEqual(event['source_pts_seconds'],[42+59/60,43.])
            self.assertEqual(event['template_evidence'],reference['evidence'])
            # No missing full-frame cache may make the old masked band acceptable.
            (root/'native-features/manifest.json').unlink()
            self.assertEqual(observe_processing(data,root/'processing-features.npz')['notes'][0]['reason'],
                             'insufficient_clear_approach')
            self.assertEqual(data,original)
            self.assertEqual((root/'source.mkv').read_bytes(),b'unchanged recording')

    def test_hud_only_observations_or_short_tracks_do_not_supply_a_template(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);data,times,pts=fixture(root)
            data['notes'][0]['points']=[p for p in data['notes'][0]['points']if 65<=p[1]<=90]
            self.assertEqual(learn(data,root,times,pts),{})
            data['notes'][0]['points']=data['notes'][0]['points'][:2]
            self.assertEqual(learn(data,root,times,pts),{})

    def test_mismatched_native_timestamps_or_source_contract_fail_explicitly(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);data,times,pts=fixture(root)
            for changed_times,changed_pts in ((times+.01,pts),(times,pts+.01),(times[:-1],pts[:-1])):
                with self.assertRaisesRegex(ValueError,'Processing template native'):
                    learn(data,root,changed_times,changed_pts)
            data['media']['path']='another recording'
            with self.assertRaisesRegex(ValueError,'source/geometry contract'):learn(data,root,times,pts)
