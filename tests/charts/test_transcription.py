"""Native chart projection feeds sustained holds into TypeScript drafting."""
import unittest
from piu_timeline.charts import ucs
from piu_timeline.charts.data import draft
from tests.charts.test_data import data, prove_types


class TranscriptionTest(unittest.TestCase):
    def test_hold_body_crosses_measure_and_tempo_boundaries_without_new_presses(self):
        source=data()
        source['hold_analysis']={'holds':[{'id':0,'lane':2,'start_range':[11.49,11.51],
            'end_range':[12.495,12.505],'start_censored':False,'end_censored':False,
            'head_note':2,'covered_notes':[2],'input':{'segments':[]}}]}
        prove_types(source,holds={2})
        timing=ucs.parse(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=1\n'
                         +4*'.....\n'+':BPM=240\n'+4*'.....\n')
        document,proof=draft(timing,source,{'song_start_seconds':10,'uncertainty_seconds':0})
        cells=[(float(t),document.sections[si].rows[ri][2])for si,ri,t in document.grid()]
        self.assertIn((1.5,'M'),cells);self.assertIn((2.5,'W'),cells)
        self.assertTrue(all(cell=='H' for t,cell in cells if 1.5<t<2.5))
        self.assertEqual(proof['summary']['placed_holds'],1)
