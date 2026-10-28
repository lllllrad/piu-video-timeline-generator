"""A single unsupported source-clock row can use independently fixed neighbors."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.play.beats.coordinates import prepare
from piu_timeline.play.beats.recovery import recover
from piu_timeline.play.beats.timing import apply
from tests.play.beats.test_recovery import scenario


class UnsupportedRecoveryTest(unittest.TestCase):
    def test_partial_group_neighbors_prove_a_row_without_reusing_the_failed_head(self):
        for invalid in (False,True):
            data=scenario();notes=data['notes']
            for i,note in enumerate(notes):
                target=1+i*.125
                note['video_target_range']=[target-.001,target+.001]
                note['beat_reconstruction']={'status':'restored','group_index':0}
            notes[4].update(reason='beat_timing_reconstruction_failed',
                            video_target_range=[1.53,1.55],
                            beat_reconstruction={'status':'failed','group_index':0,'reason':'no_natural_beat_subdivision'})
            if invalid:
                t,y=notes[4]['points'][0];notes[4]['points'][0]=(t,y+3)
            group={'status':'partial','notes':list(range(9)),'unsupported_indices':[4],
                   'unconstrained_row_domains':[[8+i,8+i]if i!=4 else[13,12]for i in range(9)]}
            support=prepare(data,40,include_failed=True);original=deepcopy(notes)
            results=recover(notes,support,[(0,4,120)],0,0,0,groups=[group])
            with self.subTest(invalid_native=invalid):
                if invalid:
                    self.assertNotIn(4,results);self.assertEqual(notes,original)
                else:
                    self.assertEqual(notes[4]['target_seconds'],1.5)
                    self.assertEqual(notes[4]['points'],original[4]['points'])
                    self.assertEqual(results[4]['excluded_reference_group'],[4])
                    refs=results[4]['models'][0]['model']['references']
                    self.assertNotIn(4,[r['note']for r in refs])
                    self.assertGreaterEqual(len(refs),5)
                    self.assertEqual(results[4]['source_timing']['range'],[1.53,1.55])
                    self.assertFalse(results[4]['source_timing']['independent'])

    def test_unsupported_and_ambiguous_clock_rows_keep_distinct_failure_reasons(self):
        targets=[1+i*.125+.02 for i in range(12)];errors=[.03]*12
        targets.insert(6,1+.625+1/12);errors.insert(6,.01);errors[9]=.14
        data={'notes':[{'lane':0,'status':'estimated','points':[[.1,200]],
                        'target_seconds':t,'prediction_uncertainty_seconds':e}for t,e in zip(targets,errors)]}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);timing=root/'timing.ucs'
            timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*32)
            ref={'status':'available','timing':str(timing),'song_start_seconds':1,'alignment_uncertainty_seconds':0}
            with patch('piu_timeline.play.beats.timing.reference',return_value=ref):result=apply(data,root)
        self.assertEqual(result['notes'][6]['beat_reconstruction']['reason'],'no_natural_beat_subdivision')
        self.assertEqual(result['notes'][9]['beat_reconstruction']['reason'],'ambiguous_beat_rows')
        self.assertEqual({i for i,n in enumerate(result['notes'])if n['status']=='excluded'},{6,9})
