"""Chart-derived observations survive storage, geometry changes and UCS row reconstruction."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from piu_timeline.play.beats.timing import apply
from piu_timeline.charts.ucs import parse
from piu_timeline.charts.transcription import transcribe
from tests.play.beats.fixtures import native_scene


class NativeSceneTest(unittest.TestCase):
    def reconstruct(self,events,spacing,fps,lanes,root):
        source=json.loads(json.dumps(native_scene(events,spacing,fps,lanes)))
        before=json.dumps(source,sort_keys=True)
        path=root/'timing.ucs'
        path.write_text(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=4\n'+'.....\n'*64)
        ref={'status':'available','timing':str(path),'song_start_seconds':0,'alignment_uncertainty_seconds':0}
        with patch('piu_timeline.play.beats.timing.reference',return_value=ref):result=apply(source,root)
        self.assertEqual(json.dumps(source,sort_keys=True),before)
        self.assertEqual([n['points']for n in result['notes']],[n['points']for n in source['notes']])
        self.assertEqual(result['scroll_motion'],source['scroll_motion'])
        self.assertEqual(result['head_registration'],source['head_registration'])
        return source,json.loads(json.dumps(result)),parse(path.read_text())

    def test_natural_rhythms_and_chords_keep_every_note_through_ucs_rows(self):
        with tempfile.TemporaryDirectory()as tmp:
            for divisions in (3,4):
                for spacing in (20.,40.,80.):
                    for fps in (30,60,120):
                        for lanes in (5,10):
                            events=[(1+i*.5/divisions,i%lanes)for i in range(2*divisions+1)]
                            events.insert(1,(1.,lanes-1))
                            with self.subTest(divisions=divisions,spacing=spacing,fps=fps,lanes=lanes):
                                _,result,template=self.reconstruct(events,spacing,fps,lanes,Path(tmp))
                                self.assertEqual(result['beat_timing']['warnings'],[])
                                self.assertTrue(all(n['status']=='estimated'for n in result['notes']))
                                self.assertEqual(len(result['notes']),len(events))
                                intervals={(i,'head'):[n['target_seconds']-n['prediction_uncertainty_seconds'],
                                                       n['target_seconds']+n['prediction_uncertainty_seconds']]
                                           for i,n in enumerate(result['notes'])}
                                _,grid,rows,failures,_=transcribe(template,intervals)
                                self.assertEqual(failures,{})
                                self.assertEqual(len(rows),len(events))
                                for i,(time,lane)in enumerate(events):
                                    self.assertAlmostEqual(result['notes'][i]['target_seconds'],time)
                                    self.assertEqual(result['notes'][i]['lane'],lane)
                                    self.assertAlmostEqual(float(grid[rows[i,'head']][2]),time)

    def test_a_close_stagger_is_restored_or_explicitly_failed_never_silently_collapsed(self):
        events=[(1.,0),(1.+1/64,1)]+[(1+i*.125,i%5)for i in range(1,9)]
        with tempfile.TemporaryDirectory()as tmp:
            for spacing in (20.,40.,80.):
                for fps in (30,60,120):
                    with self.subTest(spacing=spacing,fps=fps):
                        _,result,_=self.reconstruct(events,spacing,fps,5,Path(tmp))
                        for i in (0,1):
                            note=result['notes'][i]
                            if note['status']=='estimated':self.assertAlmostEqual(note['target_seconds'],events[i][0])
                            else:self.assertTrue(any(w['note']==i for w in result['beat_timing']['warnings']))
