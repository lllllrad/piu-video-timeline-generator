import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
import numpy as np

from piu_timeline.play import analysis as play
from piu_timeline.play.judgments import VERSION as JUDGMENT_VERSION
from piu_timeline.play.judgments import cache_contracts


class PlayCacheTest(unittest.TestCase):
    def setUp(self):
        repository=tempfile.TemporaryDirectory()
        self.addCleanup(repository.cleanup)
        isolated=patch('piu_timeline.charts.data.default_repository',return_value=Path(repository.name)/'missing')
        isolated.start();self.addCleanup(isolated.stop)

    def test_renumbered_play_reuses_input_matched_snapshot_and_relocates_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source.mkv';source.write_bytes(b'original')
            media={'path':str(source),'size_bytes':source.stat().st_size,'mtime_ns':source.stat().st_mtime_ns}
            segment={'start_seconds':1.,'end_seconds':2.,'song':'Corrected','chart':'S2','players':{}}
            directory=root/'data/id';(directory/'analysis').mkdir(parents=True)
            roi=[0,0,320,180]
            (directory/'analysis/analysis.json').write_text(json.dumps({'media':media,'game_roi':roi,'segments':[{'start_seconds':0,'end_seconds':1},segment]}))
            donor=directory/'play/segment-001.previous-example';(donor/'evidence').mkdir(parents=True)
            (donor/'evidence/proof.png').write_bytes(b'original evidence')
            layout={'receptor_y':.2,'combo_roi':[.4,.5,.2,.1],'lanes':[{'x':.1+.2*i} for i in range(5)]}
            saved={**segment,'song':'Old OCR','chart':'S1','media':media,'game_roi':roi,'analysis_width':320,
                   'analysis_height':180,'layout':layout,'frame_count':2,'participant_slots':[],
                   'frame_observation_version':play.FRAME_OBSERVATION_VERSION,
                   'judgment_events':[],'calibration':{'file':str(donor/'evidence/proof.png')}}
            from piu_timeline.play.beat_timing import FORMAT as BEAT_FORMAT, reference
            saved['beat_timing']={'status':'unavailable','contract':{'format':BEAT_FORMAT,'reference':reference(saved,donor)}}
            saved['judgment_cache']=cache_contracts(saved,[])
            (donor/'analysis.json').write_text(json.dumps(saved,indent=2))
            trace=''.join(json.dumps({'source_pts_seconds':t,'playback_seconds':t,'combo':None,'notes':[]})+'\n' for t in (1.,1.02))
            (donor/'frames.jsonl').write_text(trace)
            (donor/'judgments.jsonl').write_text(''.join(json.dumps({'playback_seconds':t,'source_pts_seconds':t,
                'label':None,'box':None,'blank':False})+'\n' for t in (1.,1.02)))
            with patch.object(play,'LOCAL_DATA',root/'data'),patch.object(play,'source_id',return_value='id'), \
                    patch.object(play,'analyze_play',side_effect=AssertionError('must reuse original acquisition')):
                report=play.run('id',2,width=320)
            result=json.loads(report.with_name('analysis.json').read_text())
            self.assertEqual(result['segment_number'],2)
            self.assertEqual(result['song'],'Corrected')
            self.assertEqual(report.with_name('frames.jsonl').read_text(),trace)
            self.assertEqual(Path(result['calibration']['file']),report.parent/'evidence/proof.png')
            self.assertEqual(Path(result['calibration']['file']).read_bytes(),b'original evidence')
            self.assertEqual((donor/'evidence/proof.png').read_bytes(),b'original evidence')

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
            saved={**segment,'media':media,'game_roi':[0,0,320,180],'play_analysis_version':play.VERSION,'timing_format':play.TIMING_FORMAT,'frame_observation_version':play.FRAME_OBSERVATION_VERSION,
                   'analysis_width':320,'analysis_height':180,'player':None,'participant_slots':[],
                   'layout':layout,'frame_count':2,'display_delay_correction_ms':0,
                   'judgment_analysis_version':JUDGMENT_VERSION,'judgment_template_labels':[],'judgment_events':[]}
            saved['play_analysis_version']='unrelated application release'
            from piu_timeline.play.beat_timing import FORMAT as BEAT_FORMAT, reference
            saved['beat_timing']={'status':'unavailable','contract':{'format':BEAT_FORMAT,'reference':reference(saved,final)}}
            saved['judgment_cache']=cache_contracts(saved,[])
            (final/'analysis.json').write_text(json.dumps(saved))
            trace=''.join(json.dumps({'source_pts_seconds':t,'playback_seconds':t,'notes':[],'combo':None})+'\n' for t in (1.,1.02))
            (final/'frames.jsonl').write_text(trace)
            (final/'judgments.jsonl').write_text(''.join(json.dumps({'playback_seconds':t,'source_pts_seconds':t,
                'label':None,'box':None,'blank':False})+'\n' for t in (1.,1.02)))
            segment.update(song='Corrected title',chart='S2')
            (directory/'analysis/analysis.json').write_text(json.dumps({'media':media,'game_roi':[0,0,320,180],'segments':[segment]}))
            with patch.object(play,'LOCAL_DATA',root/'data'),patch.object(play,'source_id',return_value='id'), \
                    patch.object(play,'analyze_play',side_effect=AssertionError('must reuse observations')):
                play.run('id',width=320,display_delay_ms=30)
            result=json.loads((final/'analysis.json').read_text())
            self.assertEqual(result['play_analysis_version'],play.VERSION)
            self.assertEqual(result['display_delay_correction_ms'],30)
            self.assertEqual(result['song'],'Corrected title')
            self.assertEqual(result['chart'],'S2')
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
            saved={**segment,'media':media,'game_roi':document['game_roi'],'play_analysis_version':play.VERSION,'timing_format':play.TIMING_FORMAT,
                   'analysis_width':650,'player':None,'participant_slots':[],'judgment_analysis_version':JUDGMENT_VERSION,'judgment_template_labels':[],'judgment_events':[]}
            saved['layout']={'lanes':[{'x':.1+.2*i} for i in range(5)],'combo_roi':[.4,.5,.2,.1]}
            from piu_timeline.play.beat_timing import FORMAT as BEAT_FORMAT, reference
            saved['beat_timing']={'status':'unavailable','contract':{'format':BEAT_FORMAT,'reference':reference(saved,final)}}
            saved['judgment_cache']=cache_contracts(saved,[])
            (final/'analysis.json').write_text(json.dumps(saved))
            with patch.object(play,'LOCAL_DATA',root/'data'),patch.object(play,'source_id',return_value='id'), \
                    patch.object(play,'analyze_play',side_effect=AssertionError('must reuse evidence')):
                report=play.run('id')
            self.assertEqual(report,final/'report.html')
            self.assertTrue(report.is_file())

    def test_word_association_upgrade_does_not_refit_notes_or_rewrite_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'recording.mkv';source.write_bytes(b'original')
            stat=source.stat();media={'path':str(source),'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns}
            segment={'start_seconds':1,'end_seconds':2,'song':'Example','chart':'S1','players':{}}
            directory=root/'data/id';(directory/'analysis').mkdir(parents=True)
            roi=[0,0,320,180]
            (directory/'analysis/analysis.json').write_text(json.dumps({'media':media,'game_roi':roi,'segments':[segment]}))
            final=directory/'play/segment-001';final.mkdir(parents=True)
            saved={**segment,'media':media,'game_roi':roi,'analysis_width':650,'player':None,'participant_slots':[],
                   'play_analysis_version':play.VERSION,'timing_format':play.TIMING_FORMAT,
                   'notes':[],'matches':[],'coverage':{},'combo_events':[],'judgment_events':[],
                   'layout':{'lanes':[{'x':.1+.2*i} for i in range(5)],'combo_roi':[.4,.5,.2,.1]}}
            from piu_timeline.play.beat_timing import FORMAT as BEAT_FORMAT, reference
            saved['beat_timing']={'status':'unavailable','contract':{'format':BEAT_FORMAT,'reference':reference(saved,final)}}
            saved['judgment_cache']=cache_contracts(saved,[])
            saved['judgment_cache']['association']['format']={'schema':1,'revision':0}
            (final/'analysis.json').write_text(json.dumps(saved))
            raw=json.dumps({'playback_seconds':1,'source_pts_seconds':41,'label':None,'blank':False})+'\n'
            (final/'judgments.jsonl').write_text(raw)
            with patch.object(play,'LOCAL_DATA',root/'data'),patch.object(play,'source_id',return_value='id'), \
                    patch.object(play,'refit_saved',side_effect=AssertionError('note trajectories are already current')), \
                    patch.object(play,'analyze_play',side_effect=AssertionError('must not reacquire frames')):
                report=play.run('id')
            result=json.loads(report.with_name('analysis.json').read_text())
            self.assertEqual(result['judgment_cache'],cache_contracts(result,[]))
            self.assertEqual((final/'judgments.jsonl').read_text(),raw)
            self.assertEqual((source.read_bytes(),source.stat().st_mtime_ns),(b'original',stat.st_mtime_ns))

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

    def test_judgment_reference_requires_all_fields_and_one_selected_player(self):
        names = ('perfect', 'great', 'good', 'bad', 'miss')
        result = {name: value for name, value in zip(names, (1071, 22, 3, 1, 3))}
        result['fields'] = {name: {'status': 'recognized'} for name in names}
        segment = {'results': {'players': {'p2': result}}}
        self.assertEqual(play.result_reference(segment)['total'], 1100)
        segment['results']['players']['p1'] = result
        self.assertIsNone(play.result_reference(segment))
        self.assertEqual(play.result_reference(segment, 'p2')['total'], 1100)
        result['fields']['miss']['status'] = 'unknown'
        self.assertIsNone(play.result_reference(segment, 'p2'))
