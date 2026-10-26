"""Tail resemblance and current processing support are independent facts."""
import json
from pathlib import Path
import tempfile
import unittest

from piu_timeline.tools.visual_support_review import recording_rows, render


class SkinReviewTest(unittest.TestCase):
    def test_distinct_tail_is_not_rejected_visually_and_unreviewed_plays_are_not_promoted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);directory=root/'source';(directory/'analysis').mkdir(parents=True)
            media={'path':str(directory/'raw/video.mkv'),'size_bytes':10,'mtime_ns':20}
            document={'media':media,'segments':[{'start_seconds':n*10,'end_seconds':n*10+5,
                       'song':'Observed title','chart':'S10'}for n in range(3)]}
            (directory/'analysis/analysis.json').write_text(json.dumps(document))
            profile={'schema':1,'media':{'size_bytes':10,'mtime_ns':20},'regions':[
                {'start_seconds':0,'end_seconds':5,'chart_geometry':False,'reason':'Endpoint detector missing'}],
                'reviews':[{'segment_number':1,'tail_appearance':'distinct_endpoint',
                            'observation':'A flat end differs from the tap glyph'},
                           {'segment_number':2,'tail_appearance':'tap_like',
                            'observation':'Same glyph requires temporal body evidence'}]}
            path=directory/'visual-support.json';path.write_text(json.dumps(profile))
            rows=recording_rows(directory)
            self.assertEqual(rows[0]['tail_appearance'],'distinct_endpoint')
            self.assertEqual(rows[0]['ucs_block_reasons'],['Endpoint detector missing'])
            self.assertEqual(rows[1]['tail_appearance'],'tap_like')
            self.assertEqual(rows[2]['tail_appearance'],'not_reviewed')
            self.assertIn('not verified UCS support',render(rows,root/'index.html'))
            profile['regions'].append({'start_seconds':10,'end_seconds':15,'chart_geometry':False,
                                       'reason':'Newly confirmed false hold'})
            path.write_text(json.dumps(profile))
            self.assertEqual(recording_rows(directory)[1]['ucs_block_reasons'],['Newly confirmed false hold'])
            profile['media']['mtime_ns']=21;path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(ValueError,'stale source identity'):recording_rows(directory)
