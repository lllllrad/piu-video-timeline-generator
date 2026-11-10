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
            data={'start_seconds':10,'end_seconds':20,'notes':[{'status':'estimated','lane':0,'points':[[10,100]],'target_seconds':10.25,'prediction_uncertainty_seconds':.001}]}
            from piu_timeline.derived import call
            from piu_timeline.play.stages import save_coordinates
            original=data
            source=call('stageCoordinates.capture',data,str(root.resolve())+'/')
            physical=call('physicalTiming.capture',source,data)['physical_timing']
            data=save_coordinates(data,root)
            (root/'physical-timing.json').write_text(json.dumps(physical))
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
            self.assertEqual(failure['notes'],original['notes'])
