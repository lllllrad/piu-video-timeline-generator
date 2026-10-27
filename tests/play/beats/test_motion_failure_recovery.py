"""A rejected time conversion does not invalidate independently measured pixels."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.play.beats.coordinates import prepare
from piu_timeline.play.beats.timing import apply
from tests.play.beats.test_recovery import scenario


class MotionFailureRecoveryTest(unittest.TestCase):
    def test_spacing_failure_requires_new_native_proof_and_retires_only_its_own_warning(self):
        for invalid in (False, True):
            data=scenario();note=data['notes'][4]
            reason='shared_spacing_reconstruction_conflict'
            note['reason']=reason;note['timing_reconstruction']['reason']=reason
            data['timing_reconstruction']['warnings'][0]['reason']=reason
            other={'note':4,'reason':'shared_motion_observation_conflict'}
            data['timing_reconstruction']['warnings'].append(other)
            if invalid:
                t,y=note['points'][0];note['points'][0]=(t,y+3)
            original=deepcopy(data)
            self.assertNotIn(4,prepare(data,40)['chunks'][0])
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);timing=root/'timing.ucs'
                timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*32)
                reference={'status':'available','timing':str(timing),'song_start_seconds':0,'alignment_uncertainty_seconds':0}
                with patch('piu_timeline.play.beats.timing.reference',return_value=reference):result=apply(data,root)
            with self.subTest(invalid_native=invalid):
                warnings=result['timing_reconstruction']['warnings']
                if invalid:
                    self.assertEqual(result['notes'][4]['status'],'excluded')
                    self.assertIn({'note':4,'reason':reason},warnings)
                else:
                    self.assertEqual(result['notes'][4]['target_seconds'],1.5)
                    self.assertEqual(warnings,[other])
                    self.assertEqual(result['timing_reconstruction']['restored_notes'],9)
                    proof=next(p for p in result['beat_timing']['native_coordinate_recovery']if p['note']==4)
                    self.assertEqual(proof['source_failure'],reason)
                    self.assertTrue(all(4 not in [r['note']for r in model['model']['references']]for model in proof['models']))
                self.assertEqual(data,original)
