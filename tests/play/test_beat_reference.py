"""Native audio preparation and read-only reference-cache orchestration."""
import unittest
from hashlib import sha256


class BeatReferenceTest(unittest.TestCase):
    def test_audio_alignment_is_prepared_without_chart_regions_and_current_checks_stay_read_only(self):
        from pathlib import Path
        import tempfile,json
        from unittest.mock import patch
        from piu_timeline.play.beats.timing import apply,current,validate_physical,prepare_input
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);metadata=root/'metadata.json';metadata.write_text(json.dumps({'regions':[]}))
            timing=root/'timing.ucs';timing.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Beat=4\n:Split=4\n'+'.....\n'*32)
            missing={'status':'unavailable','reason':'verified_song_alignment_missing','ucs_index':'CS999','metadata_path':str(metadata)}
            ready={'status':'available','timing':str(timing),'sha256':sha256(timing.read_bytes()).hexdigest(),'song_start_seconds':10,'alignment_uncertainty_seconds':0}
            data={'start_seconds':10,'end_seconds':20,'analysis_width':400,'analysis_height':400,
                  'layout':{'receptor_y':.1,'note_y_max':.95,'lanes':[{'x':.1+.1*i}for i in range(5)]},
                  'frame_timeline':[{'time':10+i/60,'source_pts':100+i/60}for i in range(61)],
                  'notes':[{'lane':0,'points':[[10+i/60,100-240*i/60]for i in range(10)]}]}
            from piu_timeline.play.stages import save_coordinates,physical_timing
            data=physical_timing(save_coordinates(data,root),root)
            data=validate_physical(data,root)
            with patch('piu_timeline.play.beats.timing.reference',side_effect=[missing,ready]),patch('piu_timeline.charts.audio.prepare_alignment') as align:
                result=apply(prepare_input(data,root),root)
            align.assert_called_once()
            self.assertEqual(result['beat_timing']['status'],'restored')
            self.assertEqual(result['beat_timing']['reference_preparation']['status'],'prepared')
            with patch('piu_timeline.play.beats.timing.reference',return_value=ready),patch('piu_timeline.charts.audio.prepare_alignment',side_effect=AssertionError('Current checks must not read audio')):
                self.assertTrue(current(result,root))
            with patch('piu_timeline.play.beats.timing.reference',return_value=missing),patch('piu_timeline.charts.audio.prepare_alignment',side_effect=ValueError('Independent audio windows disagree')):
                failure=apply(prepare_input(data,root),root)
            self.assertEqual(failure['beat_timing']['status'],'unavailable')
            self.assertEqual(failure['beat_timing']['warnings'][0]['failure_detail'],'Independent audio windows disagree')
            self.assertAlmostEqual(failure['notes'][0]['target_seconds'],10.25)
            self.assertEqual(failure['notes'][0]['status'],'estimated')
