"""Coordinate artifacts resume only their bound source and producer output."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from piu_timeline.play.stages import load_coordinates,save_coordinates


class CoordinateStageTest(unittest.TestCase):
    def test_coordinate_boundary_survives_promotion_and_ignores_downstream_rules(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);pending=root/'build';pending.mkdir()
            source={'media':{'path':'source.mkv','mtime_ns':1780000000000000001},
                    'notes':[{'lane':0,'points':[[1,100]],'target_seconds':2}],
                    'timing_format':{'coordinates':1},'head_registration':{'evidence':str(pending/'evidence/proof.npz')},
                    'matches':[]}
            saved=save_coordinates(source,pending);original=deepcopy(saved)
            final=root/'segment';pending.rename(final)
            saved['head_registration']['evidence']=str(final/'evidence/proof.npz')
            saved['notes'][0]['target_seconds']=99
            saved['beat_timing']={'contract':{'format':'different beat rules'}}
            resumed=load_coordinates(saved,final)
            self.assertEqual(resumed['notes'][0]['target_seconds'],2)
            self.assertEqual(resumed['media'],original['media'])
            self.assertEqual(resumed['head_registration']['evidence'],str(final/'evidence/proof.npz'))
            self.assertEqual(saved['notes'][0]['target_seconds'],99)
            saved['timing_format']={'coordinates':2}
            self.assertIsNone(load_coordinates(saved,final))

    def test_corrupted_output_cannot_silently_resume(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);saved=save_coordinates({'notes':[]},root)
            path=root/'coordinates.json';payload=json.loads(path.read_text())
            payload['output']['notes']=[{'lane':4}]
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError,'fingerprint'):load_coordinates(saved,root)
