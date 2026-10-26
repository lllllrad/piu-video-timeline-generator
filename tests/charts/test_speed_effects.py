"""Measured motion stays distinct from nominal BPM and human chart decisions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.charts.speed_effects import proposals, record
from piu_timeline.play.speed_estimation import estimate
from piu_timeline.tools.chart_motion import review
from tests.play.test_speed_estimation import scenario


class SpeedEffectsTest(unittest.TestCase):
    def fixture(self, root):
        repository=root/'repo';path=repository/'charts/example/S20/current/metadata.json'
        path.parent.mkdir(parents=True)
        timing=repository/'timing/example.ucs';timing.parent.mkdir()
        timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Beat=4\n:Split=1\n'+5*'.....\n'+':BPM=240\n.....\n')
        media=root/'recording';media.write_bytes(b'unchanged source');stat=media.stat()
        source={'source_id':'video','segment_number':1,'media_size_bytes':stat.st_size,'media_mtime_ns':stat.st_mtime_ns}
        metadata={'source':source,'identity':{'ucs_index':'example'},
                  'alignment':{'song_start_seconds':999.5,'rate':1,'uncertainty_seconds':.02},
                  'regions':[],'human_field':'preserve'}
        path.write_text(json.dumps(metadata))
        data={**scenario(1.73),'segment_number':1,
              'media':{'path':str(media),'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns}}
        directory=root/'.local/data/video/play/segment-001';directory.mkdir(parents=True)
        (directory/'analysis.json').write_text(json.dumps(data))
        return repository,path,timing,metadata,data

    def test_bpm_and_measured_ratio_remain_separate_and_review_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository,path,timing,metadata,data=self.fixture(Path(temporary))
            candidates=proposals(estimate(data),metadata,timing,metadata['source'])
            self.assertEqual(len(candidates),1)
            effect=candidates[0];context=effect['evidence'][0]['ucs_bpm_context']
            self.assertEqual(context['nominal_bpm_ratio'],2)
            self.assertAlmostEqual(effect['speed_multiplier'],1.73,delta=.02)
            self.assertAlmostEqual(context['measured_ratio_divided_by_bpm_ratio'],1.73/2,delta=.01)
            self.assertLess(effect['transition_range_seconds'][0],2.5-.019)
            self.assertGreater(effect['transition_range_seconds'][1],2.5+.019)
            self.assertTrue(record(repository,path,candidates))
            saved=json.loads(path.read_text());saved['gimmick_candidates'][0]['review_status']='rejected'
            path.write_text(json.dumps(saved));original=path.read_bytes()
            self.assertFalse(record(repository,path,candidates))
            self.assertEqual(path.read_bytes(),original)
            second=deepcopy(candidates);second[0]['evidence'][0]['source_id']='another-source'
            self.assertTrue(record(repository,path,second))
            saved=json.loads(path.read_text())
            self.assertEqual(saved['gimmick_candidates'][0]['review_status'],'rejected')
            self.assertEqual(len(saved['gimmick_candidates'][0]['evidence']),2)
            self.assertEqual(saved['regions'],[])
            self.assertEqual(saved['human_field'],'preserve')
            upgraded=deepcopy(candidates);upgraded[0]['evidence'][0]['coordinate_registration']={'model':'refined_native_positions'}
            self.assertTrue(record(repository,path,upgraded))
            saved=json.loads(path.read_text())
            self.assertEqual(len(saved['gimmick_candidates'][0]['evidence']),3)
            self.assertEqual(saved['gimmick_candidates'][0]['review_status'],'rejected')
            self.assertFalse(record(repository,path,upgraded))

    def test_review_uses_only_saved_motion_and_rejects_changed_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,path,_,_,data=self.fixture(root);original=path.read_bytes()
            with patch('piu_timeline.tools.chart_motion.ROOT',root):
                result=review(path)
                self.assertEqual(len(result['candidates']),1)
                self.assertFalse(result['changed'])
                self.assertEqual(path.read_bytes(),original)
                Path(data['media']['path']).write_bytes(b'replaced source recording')
                with self.assertRaisesRegex(ValueError,'Source identity changed'):review(path,write=True)
                self.assertEqual(path.read_bytes(),original)

    def test_old_integrated_phase_cannot_be_written_as_a_chart_speed_effect(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,path,_,_,data=self.fixture(root)
            data['scroll_motion'].pop('coordinate_registration')
            (root/'.local/data/video/play/segment-001/analysis.json').write_text(json.dumps(data))
            original=path.read_bytes()
            with patch('piu_timeline.tools.chart_motion.ROOT',root):result=review(path,write=True)
            self.assertTrue(result['measurements']['transitions'])
            self.assertEqual(result['candidates'],[])
            self.assertFalse(result['changed'])
            self.assertEqual(path.read_bytes(),original)
