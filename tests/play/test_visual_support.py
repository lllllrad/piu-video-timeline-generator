"""Play options must not contaminate a song's shared chart metadata."""
import json
from pathlib import Path
import tempfile
import unittest

from piu_timeline.charts.data import auto_register
from piu_timeline.play.exclusions import recognition_diagnostics
from piu_timeline.play.support import visual_support,require_chart_geometry


class VisualSupportTest(unittest.TestCase):
    def test_source_review_blocks_ucs_only_in_affected_play_and_never_exempts_warnings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);raw=root/'video/raw';raw.mkdir(parents=True)
            profile={'schema':1,'media':{'size_bytes':100,'mtime_ns':200},'regions':[
                {'start_seconds':10,'end_seconds':20,'chart_geometry':False,
                 'reason':'Per-play reverse scrolling is not yet supported'}]}
            path=raw.parent/'visual-support.json';path.write_text(json.dumps(profile));original=path.read_bytes()
            data={'media':{'path':str(raw/'video.mkv'),'size_bytes':100,'mtime_ns':200},
                  'start_seconds':12,'end_seconds':18,'notes':[]}
            support=visual_support(data);self.assertFalse(support['chart_geometry'])
            with self.assertRaisesRegex(ValueError,'Unsupported visual profile'):require_chart_geometry(data)
            out=root/'output';out.mkdir();registered=auto_register(data,out)
            self.assertEqual(registered['status'],'pending')
            self.assertIn('reverse scrolling',registered['reason'])
            data['visual_support']=support
            data['chart_policy']={'regions':[{'id':'blanket','playback_start_seconds':0,'playback_end_seconds':30,
                                            'check_exceptions':['timing_evidence'],'processing':'exclude_timing'}]}
            result=recognition_diagnostics(data,{'notes':{}})
            self.assertEqual(result['warnings'][0]['reason'],'unsupported_visual_profile')
            data.update(start_seconds=20,end_seconds=25)
            self.assertIsNone(visual_support(data));require_chart_geometry(data)
            data['media']['mtime_ns']=201
            with self.assertRaisesRegex(ValueError,'stale source identity'):visual_support(data)
            self.assertEqual(path.read_bytes(),original)
