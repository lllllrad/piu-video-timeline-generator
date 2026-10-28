"""Coordinate artifacts resume only their bound source and producer output."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from piu_timeline.play.stages import load_coordinates,save_coordinates
from piu_timeline.play.observations.artifacts import cached
from piu_timeline.play.observations.records import retained


class NativeStageTest(unittest.TestCase):
    def test_numeric_evidence_ids_have_one_json_representation_on_first_build_and_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            value = {2: {'source_pts_seconds': 40.2}, 10: {'source_pts_seconds': 40.4}}
            first = cached(directory, 'proofs', {}, lambda: value)
            again = cached(directory, 'proofs', {}, Mock(side_effect=AssertionError('must reuse')))
            self.assertEqual(first, again)
            self.assertEqual(set(first), {'2', '10'})

    def test_consumer_records_exclude_bulky_native_image_details_and_keep_timing(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'frames.jsonl'
            native = [{'playback_seconds': time, 'source_pts_seconds': time+40, 'combo': value, 'combo_confidence': .95,
                       'skin_observations': [{'unused_comparison_details': 'x'*10000}],
                       'notes': [{'lane': 2, 'x': .5, 'y': y, 'alternatives': ['x'*10000]}]}
                      for time, value, y in ((1., 10, .5), (1.04, 11, .4))]
            path.write_text(''.join(json.dumps(f)+'\n' for f in native))
            frames = retained({}, path)
            self.assertLess(len(json.dumps(frames)), 500)
            self.assertEqual(frames[1]['notes'], [{'lane': 2, 'x': .5, 'y': .4}])
            self.assertEqual(frames[1]['source_pts_seconds'], 41.04)
            from piu_timeline.play.ranges import counter_frame_ranges
            events = counter_frame_ranges(path)
            self.assertEqual(events[0]['delta'], 1)
            self.assertEqual(events[0]['source_pts_seconds'], [41., 41.04])

    def test_retained_stage_survives_promotion_and_detects_damaged_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            pending = Path(temporary)/'build'; pending.mkdir()
            source = {'path': str(pending/'proof.npz')}
            observed = {'proof': source['path'], 'source_pts_seconds': [42.001, 42.017]}
            self.assertEqual(cached(pending, 'shape', source, lambda: observed), observed)
            final = pending.with_name('segment'); pending.rename(final)
            result = cached(final, 'shape', {'path': str(final/'proof.npz')}, Mock(side_effect=AssertionError('must reuse')))
            self.assertEqual(result, {'proof': str(final/'proof.npz'), 'source_pts_seconds': observed['source_pts_seconds']})
            artifact = final/'native-stages/shape.json'; saved = json.loads(artifact.read_text())
            saved['output']['source_pts_seconds'][0] += .1; artifact.write_text(json.dumps(saved))
            with self.assertRaisesRegex(ValueError, 'Corrupt native stage'):
                cached(final, 'shape', {'path': str(final/'proof.npz')}, Mock(side_effect=AssertionError('must fail')))


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
