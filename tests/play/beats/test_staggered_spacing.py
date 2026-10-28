"""Visually separated near-chords cannot silently collapse onto one beat row."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.play.beats.timing import apply

from piu_timeline.play.spacing_checks import spacing_failures


def scenario(gap=4.):
    times=[i/60 for i in range(9)]
    clock={'origin':0.,'velocity':500.,'intercept':0.}
    notes=[{'lane':i,'status':'estimated','target_seconds':target,
            'fit_method':'shared_scroll_clock','motion_clock':clock,
            'motion_target_phase':500*target,
            'points':[(t,500*target-500*t)for t in times]}
           for i,target in enumerate((1.,1.+gap/500))]
    motion={'samples':[{'time':t,'chunk':0}for t in times],
            'coordinate_registration':{'chunks':[{'chunk':0,'status':'fitted',
                'head_offsets':[{'note':i,'offset_pixels':500*n['target_seconds']}
                                for i,n in enumerate(notes)]}]}}
    return notes,motion


class StaggeredSpacingTest(unittest.TestCase):
    def test_eight_millisecond_stagger_survives_but_collapsed_row_is_rejected(self):
        for registered in (False,True):
            notes,motion=scenario();before=deepcopy((notes,motion))
            self.assertEqual(spacing_failures(notes,40,motion if registered else None),[])
            self.assertEqual((notes,motion),before)
            # Keep native trajectories and clock phases: only the beat result
            # is wrong. Both source intervals can still admit this same row.
            notes[1]['target_seconds']=1.
            warnings=spacing_failures(notes,40,motion if registered else None)
            self.assertEqual({w['note']for w in warnings},{0,1})
            self.assertTrue(all(w['reason']=='shared_spacing_reconstruction_conflict'for w in warnings))
            self.assertAlmostEqual(warnings[0]['observed_gap_pixels'],4.)
            self.assertAlmostEqual(warnings[0]['reconstructed_gap_pixels'],0.)

    def test_true_chord_and_unresolvable_raster_difference_are_not_separation_proof(self):
        for gap in (0.,1.,2.):
            notes,motion=scenario(gap);notes[1]['target_seconds']=1.
            self.assertEqual(spacing_failures(notes,40,motion),[])

    def test_close_heads_without_shared_coordinate_support_remain_unresolved(self):
        notes,motion=scenario();motion['coordinate_registration']['chunks']=[]
        warnings=spacing_failures(notes,40,motion)
        self.assertEqual({w['reason']for w in warnings},{'shared_spacing_model_unavailable'})

    def test_full_reconstruction_warns_when_individual_unique_rows_collapse_a_stagger(self):
        notes,motion=scenario()
        for note in notes:note['prediction_uncertainty_seconds']=.01
        data={'notes':notes,'scroll_motion':motion,'analysis_width':400,'analysis_height':400,
              'layout':{'receptor_y':.1,'lanes':[{'x':.2+.1*i}for i in range(5)]}}
        before=deepcopy(data)
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);timing=root/'timing.ucs'
            timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*32)
            ref={'status':'available','timing':str(timing),'song_start_seconds':0,'alignment_uncertainty_seconds':0}
            with patch('piu_timeline.play.beats.timing.reference',return_value=ref):result=apply(data,root)
        self.assertEqual(data,before)
        self.assertTrue(all(n['status']=='excluded'for n in result['notes']))
        self.assertEqual({w['reason']for w in result['beat_timing']['warnings']},
                         {'beat_timing_reconstruction_failed'})
        self.assertEqual(result['beat_timing']['phase_trials'][0]['consistent_targets'],0)
        self.assertTrue(all(w['failure_detail']=='ambiguous_or_unsupported_song_phase'
                            for w in result['beat_timing']['warnings']))
