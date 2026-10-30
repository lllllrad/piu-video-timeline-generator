"""Measured motion stays distinct from nominal BPM and human chart decisions."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.charts.speed_effects import proposals, record
from piu_timeline.play.speed_estimation import estimate
from piu_timeline.tools.chart_motion import review, recordings
from tests.charts.speed_fixtures import scenario


class SpeedEffectsTest(unittest.TestCase):
    def alternate(self, root, path, data):
        media=root/'alternate-recording';media.write_bytes(b'independent original recording');stat=media.stat()
        data=deepcopy(data);data.update(segment_number=4,start_seconds=1000,end_seconds=1005,
            media={'path':str(media),'size_bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns})
        directory=root/'.local/data/alternate/play/segment-004';directory.mkdir(parents=True)
        (directory/'analysis.json').write_text(json.dumps(data))
        (directory/'chart-registration.json').write_text(json.dumps({'index':'example','chart':str(path.with_name('chart.ucs'))}))
        reference=root/'reference/example.mp3';reference.parent.mkdir();reference.write_bytes(b'verified reference identity')
        alignment={'method':'reference_audio_translation','accepted_windows':2,'song_start_seconds':998.5,'rate':1,'uncertainty_seconds':.01}
        cached={'contract':{'media':data['media'],'start_seconds':1000,'end_seconds':1005,'ucs_index':'example',
                            'reference_audio_sha256':sha256(reference.read_bytes()).hexdigest()},'alignment':alignment}
        (directory/'chart-policy-alignment.json').write_text(json.dumps(cached))
        return directory,reference,cached

    def test_alternate_recording_uses_its_own_alignment_without_audio_or_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,path,_,_,data=self.fixture(root)
            directory,reference,_=self.alternate(root,path,data);original=path.read_bytes()
            with patch('piu_timeline.charts.official.DEFAULT_CACHE',reference.parent), \
                    patch('piu_timeline.charts.audio.align',side_effect=AssertionError('must not decode audio')), \
                    patch('piu_timeline.charts.official.Client.template',side_effect=AssertionError('must not fetch')):
                result=review(path,directory=directory)
            self.assertEqual(result['alignment']['song_start_seconds'],998.5)
            self.assertEqual(result['source'],'alternate');self.assertEqual(result['segment'],4)
            self.assertEqual(len(result['candidates']),1)
            effect=result['candidates'][0]
            self.assertLess(effect['transition_range_seconds'][0],3.5)
            self.assertGreater(effect['transition_range_seconds'][1],3.5)
            self.assertEqual(effect['evidence'][0]['source_id'],'alternate')
            self.assertEqual(effect['evidence'][0]['song_alignment']['song_start_seconds'],998.5)
            self.assertEqual(effect['evidence'][0]['media_size_bytes'],len(b'independent original recording'))
            self.assertEqual(path.read_bytes(),original)

    def test_alternate_alignment_never_falls_back_to_seed_or_stale_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,path,_,_,data=self.fixture(root)
            directory,reference,cached=self.alternate(root,path,data)
            for mode in ('missing','media','window','code','reference','rate','unverified'):
                bad=deepcopy(cached);cache=directory/'chart-policy-alignment.json'
                if mode=='media':bad['contract']['media']['mtime_ns']+=1
                if mode=='window':bad['contract']['start_seconds']+=1
                if mode=='code':bad['contract']['ucs_index']='different-chart'
                if mode=='reference':bad['contract']['reference_audio_sha256']='wrong-reference'
                if mode=='rate':bad['alignment']['rate']=2
                if mode=='unverified':bad['alignment']['accepted_windows']=1
                cache.write_text(json.dumps(bad))
                if mode=='missing':cache.unlink()
                with self.subTest(mode=mode),patch('piu_timeline.charts.official.DEFAULT_CACHE',reference.parent),self.assertRaises(ValueError):
                    review(path,directory=directory)

    def test_source_filter_discovers_registered_alternate_plays_not_only_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);repository,path,_,_,data=self.fixture(root)
            destination=path.parent.with_name('phoenix');path.parent.rename(destination);path=destination/'metadata.json'
            directory,_,_=self.alternate(root,path,data)
            with patch('piu_timeline.tools.chart_motion.ROOT',root):
                self.assertEqual(recordings(repository,['alternate']),[(path,directory)])
                self.assertEqual(len(recordings(repository)),2)

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
