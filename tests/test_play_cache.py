import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
import numpy as np

from piu_timeline import play_analysis as play


class PlayCacheTest(unittest.TestCase):
    def test_counter_recovery_must_fit_neighboring_original_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)
            values=[(1.,100),(1.02,None),(1.04,None),(1.06,100),(1.08,None),(1.1,101),(1.12,None),(1.5,102)]
            frames=[{'source_pts_seconds':t+5,'playback_seconds':t,'combo':value,
                     'combo_confidence':.95 if value is not None else 0,'notes':[]}
                    for t,value in values]
            trace=''.join(json.dumps(frame)+'\n' for frame in frames)
            (output/'frames.jsonl').write_text(trace)
            reader=Mock();reader.last_mode='threshold_template'
            reader.read.side_effect=[(102,.95),(100,.95),(101,.95)]
            crops=[(t+5,t,np.zeros((10,20,3),dtype='uint8')) for t,_ in values]
            cached={'media':{},'start_seconds':1,'end_seconds':2,'game_roi':[0,0,100,100],
                    'analysis_width':100,'layout':{'combo_roi':[.4,.5,.2,.1]},'frame_observation_version':2}
            with patch.object(play.DigitReader,'load',return_value=reader),patch.object(play,'decode_frames',return_value=iter(crops)):
                play.refresh_counter_observations(cached,output)
            updated=[json.loads(line) for line in (output/'frames.jsonl').read_text().splitlines()]
            self.assertEqual([f['combo'] for f in updated],[100,None,100,100,101,101,None,102])
            self.assertEqual(reader.read.call_count,3)
            self.assertEqual((output/'frames.base.jsonl').read_text(),trace)
            self.assertEqual([f['source_pts_seconds'] for f in updated],[f['source_pts_seconds'] for f in frames])

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
            saved={**segment,'media':media,'game_roi':[0,0,320,180],'play_analysis_version':play.VERSION,'frame_observation_version':play.FRAME_OBSERVATION_VERSION,
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
