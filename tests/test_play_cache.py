import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline import play_analysis as play


class PlayCacheTest(unittest.TestCase):
    def test_compatible_observations_refit_without_decode_or_ocr(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'recording.mkv';source.write_bytes(b'original')
            before=source.stat()
            media={'path':str(source),'size_bytes':before.st_size,'mtime_ns':before.st_mtime_ns}
            segment={'start_seconds':1,'end_seconds':2,'song':'Example','chart':'S1','players':{}}
            directory=root/'data/id';(directory/'analysis').mkdir(parents=True)
            (directory/'analysis/analysis.json').write_text(json.dumps({'media':media,'game_roi':[0,0,320,180],'segments':[segment]}))
            final=directory/'play/segment-001';final.mkdir(parents=True)
            layout={'receptor_y':.2,'lanes':[{'x':.1+.2*i} for i in range(5)]}
            saved={**segment,'media':media,'game_roi':[0,0,320,180],'play_analysis_version':6,
                   'analysis_width':320,'analysis_height':180,'player':None,'participant_slots':[],
                   'layout':layout,'frame_count':2,'display_delay_correction_ms':0}
            (final/'analysis.json').write_text(json.dumps(saved))
            trace=''.join(json.dumps({'playback_seconds':t,'notes':[],'combo':None})+'\n' for t in (1.,1.02))
            (final/'frames.jsonl').write_text(trace)
            with patch.object(play,'LOCAL_DATA',root/'data'),patch.object(play,'source_id',return_value='id'), \
                    patch.object(play,'analyze_play',side_effect=AssertionError('must reuse observations')):
                play.run('id',width=320,display_delay_ms=30)
            result=json.loads((final/'analysis.json').read_text())
            self.assertEqual(result['play_analysis_version'],play.VERSION)
            self.assertEqual(result['display_delay_correction_ms'],30)
            self.assertTrue(result['reused_native_observations'])
            self.assertEqual((final/'frames.jsonl').read_text(),trace)
            self.assertEqual((source.stat().st_size,source.stat().st_mtime_ns),(before.st_size,before.st_mtime_ns))

    def test_all_plays_continues_after_individual_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);directory=root/'id';(directory/'analysis').mkdir(parents=True)
            (directory/'analysis/analysis.json').write_text(json.dumps({'segments':[{},{}]}))
            with patch.object(play,'LOCAL_DATA',root),patch.object(play,'source_id',return_value='id'), \
                    patch.object(play,'run',side_effect=[ValueError('masked receptors'),None]) as run:
                with self.assertRaisesRegex(ValueError,'Failed plays: \\[1\\]'):
                    play.run_all('id')
            self.assertEqual(run.call_count,2)
            self.assertTrue((directory/'play/index.html').is_file())

    def test_matching_evidence_renders_without_decoding_or_ocr(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'recording.mkv';source.write_bytes(b'original')
            media={'path':str(source),'size_bytes':source.stat().st_size,'mtime_ns':source.stat().st_mtime_ns}
            segment={'start_seconds':1,'end_seconds':2,'song':'Example','chart':'S1','players':{}}
            document={'media':media,'game_roi':[0,0,320,180],'segments':[segment]}
            directory=root/'data/id';(directory/'analysis').mkdir(parents=True)
            (directory/'analysis/analysis.json').write_text(json.dumps(document))
            final=directory/'play/segment-001';final.mkdir(parents=True)
            saved={**segment,'media':media,'game_roi':document['game_roi'],'play_analysis_version':play.VERSION,
                   'analysis_width':650,'player':None,'participant_slots':[]}
            (final/'analysis.json').write_text(json.dumps(saved))
            with patch.object(play,'LOCAL_DATA',root/'data'),patch.object(play,'source_id',return_value='id'), \
                    patch.object(play,'analyze_play',side_effect=AssertionError('must reuse evidence')):
                report=play.run('id')
            self.assertEqual(report,final/'report.html')
            self.assertTrue(report.is_file())

    def test_failed_rebuild_preserves_the_previous_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);directory=root/'id';(directory/'analysis').mkdir(parents=True)
            (directory/'analysis/analysis.json').write_text(json.dumps({'segments':[{}]}))
            final=directory/'play/segment-001';final.mkdir(parents=True);(final/'report.html').write_text('previous')
            with patch.object(play,'LOCAL_DATA',root),patch.object(play,'source_id',return_value='id'), \
                    patch.object(play,'analyze_play',side_effect=ValueError('unsupported skin')):
                # Segment bounds are required before starting a build.
                data={'segments':[{'start_seconds':0,'end_seconds':1}]}
                (directory/'analysis/analysis.json').write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'unsupported skin'):
                    play.run('id')
            self.assertEqual((final/'report.html').read_text(),'previous')
