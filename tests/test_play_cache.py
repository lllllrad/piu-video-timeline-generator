import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline import play_analysis as play


class PlayCacheTest(unittest.TestCase):
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
