"""Suspected effects retain source evidence and never create check exceptions."""
import json
from pathlib import Path
import tempfile
import unittest

from piu_timeline.charts.gimmicks import record_candidates, validate_candidates
from piu_timeline.charts.policy import attach_regions
from piu_timeline.play.exclusions import recognition_diagnostics


class GimmickTest(unittest.TestCase):
    def fixture(self,root):
        output=root/'video/play/segment-001';output.mkdir(parents=True)
        repo=root/'repo';chart=repo/'charts/CS306/D22/phoenix/chart.ucs';chart.parent.mkdir(parents=True)
        chart.write_text('original editable notes')
        metadata={'source':{'source_id':'video','segment_number':1,'media_size_bytes':100,'media_mtime_ns':200},
                  'alignment':{'song_start_seconds':10},'regions':[], 'human_field':'keep'}
        chart.with_name('metadata.json').write_text(json.dumps(metadata))
        (repo/'catalog.json').write_text(json.dumps({'songs':[{'title':'Example','index':'CS306'}]}))
        (repo/'aliases.json').write_text('{}')
        data={'song':'Example','chart':'D22','segment_number':1,'media':{'size_bytes':100,'mtime_ns':200},
              'start_seconds':10,'end_seconds':30,'notes':[{'lane':0,'status':'estimated','target_seconds':13}],
              'visual_channels':{'processing':{'notes':[{'note':0,'status':'unresolved','reason':'pre_receptor_visibility_boundary','id':'processing:0','visibility_loss':{'source_pts_seconds':[52,52.017]}}],
                  'visibility_boundaries':[{'playback_range':[12,14], 'notes':[0],'last_visible_height_spacing':[.8,.9]}]}}}
        return output,chart,data,{'chart':str(chart),'repository':str(repo)}

    def test_candidates_are_deduplicated_preserve_review_decisions_and_do_not_suppress(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);output,chart,data,registration=self.fixture(root)
            self.assertTrue(record_candidates(data,output,registration)['changed'])
            saved=json.loads(chart.with_name('metadata.json').read_text())
            candidate=saved['gimmick_candidates'][0]
            self.assertEqual(candidate['review_status'],'pending')
            self.assertEqual((candidate['start_seconds'],candidate['end_seconds']),(2,4))
            self.assertEqual(candidate['evidence'][0]['loss_source_pts_ranges'],[[52,52.017]])
            candidate['review_status']='rejected';saved['human_field']='edited'
            chart.with_name('metadata.json').write_text(json.dumps(saved))
            self.assertFalse(record_candidates(data,output,registration)['changed'])
            self.assertEqual(json.loads(chart.with_name('metadata.json').read_text()),saved)
            self.assertEqual(chart.read_text(),'original editable notes')
            view=attach_regions(data,output,Path(registration['repository']))
            self.assertEqual(view['chart_policy']['gimmick_candidates'][0]['review_status'],'rejected')
            view['note_type_diagnostics']=[{'note':0,'lane':0,'reason':'note_type_conflict',
                                          'visible_start_seconds':12,'visible_end_seconds':13}]
            self.assertEqual({r['reason'] for r in recognition_diagnostics(view,{'notes':{}})['warnings']},
                             {'note_type_conflict','note_processing_unresolved'})
            self.assertEqual(saved['regions'],[])

    def test_unknown_song_alignment_is_kept_local_instead_of_guessing_chart_times(self):
        with tempfile.TemporaryDirectory() as temporary:
            output,chart,data,registration=self.fixture(Path(temporary))
            original=chart.with_name('metadata.json').read_bytes()
            data['media']['mtime_ns']=999
            result=record_candidates(data,output,registration)
            self.assertEqual(result['status'],'song_alignment_required')
            self.assertEqual(chart.with_name('metadata.json').read_bytes(),original)
            self.assertTrue((output/'gimmick-candidates.json').is_file())

    def test_invalid_candidates_cannot_be_mapped(self):
        for value in (None,[{}],[{'id':'a','kind':'visibility','reason':'review','review_status':'pending',
                                 'start_seconds':2,'end_seconds':1}]):
            with self.assertRaises(ValueError):validate_candidates({'gimmick_candidates':value})
