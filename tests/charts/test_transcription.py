"""Musical grids preserve chords and fail explicitly beyond measured precision."""
from copy import deepcopy
from fractions import Fraction
import unittest

from piu_timeline.charts import ucs
from piu_timeline.charts.data import draft
from piu_timeline.charts.transcription import transcribe
from tests.charts.test_data import data, prove_types


def template(split=48, rows=384):
    return ucs.parse(f':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split={split}\n'+rows*'.....\n')


def intervals(values, error):
    return {(i,'head'):[t-error,t+error] for i,t in enumerate(values)}


def duration(document):
    settings={}
    for section in document.sections:settings.update(section.directives)
    return list(document.grid())[-1][2]+60/(Fraction(settings['BPM'])*int(settings['Split']))


class TranscriptionTest(unittest.TestCase):
    def test_each_measure_uses_its_own_smallest_supported_split_and_shared_chord_row(self):
        source=template();points=intervals([.25,.75,.754,2+1/6,2+1/3],.006)
        original=deepcopy(points)
        document,grid,rows,failed,proof=transcribe(source,points)
        self.assertEqual(points,original)
        self.assertEqual([m['split']for m in proof['measures']],[2,3])
        self.assertEqual(rows[1,'head'],rows[2,'head'])
        self.assertEqual(grid[rows[1,'head']][2],Fraction(3,4))
        self.assertEqual(failed,{})
        self.assertEqual(duration(document),duration(source))
        self.assertEqual(ucs.parse(document.text()),document)

    def test_fine_grid_cannot_choose_nearest_row_from_an_ambiguous_interval(self):
        _,_,rows,failed,proof=transcribe(template(),intervals([.75,1.],.02))
        self.assertEqual(len(rows),2);self.assertEqual(failed,{})
        first=proof['measures'][0]
        self.assertEqual(first['split'],2)
        fine=next(t for t in first['tested_splits']if t['split']==48)
        self.assertEqual(fine['unique_endpoints'],0)

    def test_residual_tolerance_shrinks_with_row_duration_even_at_document_edge(self):
        points={(0,'head'):[-.001,.009]}
        coarse=transcribe(template(split=1,rows=4),points)
        fine=transcribe(template(split=48,rows=1),points)
        self.assertIn((0,'head'),coarse[2])
        self.assertNotIn((0,'head'),fine[2])
        self.assertIn((0,'head'),fine[3])
        self.assertEqual(fine[4]['measures'][0]['status'],'failed')

    def test_jitter_on_both_sides_of_a_measure_boundary_is_one_chord(self):
        _,grid,rows,failed,_=transcribe(template(),intervals([1.999,2.001],.005))
        self.assertEqual(failed,{})
        self.assertEqual(rows[0,'head'],rows[1,'head'])
        self.assertEqual(grid[rows[0,'head']][2],2)

    def test_neighboring_finer_measure_is_checked_before_accepting_boundary_note(self):
        points={(0,'head'):[1.988,2.010],(1,'head'):[2.0077125,2.0079125]}
        _,_,rows,failed,proof=transcribe(template(),points)
        self.assertNotIn((0,'head'),rows)
        self.assertIn('across measure grids',failed[0,'head'])
        self.assertIn((1,'head'),rows)
        self.assertEqual(proof['measures'][1]['split'],64)

    def test_exact_tempo_delay_and_fractional_measure_boundaries_are_preserved(self):
        source=ucs.parse(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=90\n:Beat=4\n:Split=2\n'
                         +3*'.....\n'+':BPM=180\n:Delay=10\n:Split=3\n'+12*'.....\n')
        document,grid,_,_,proof=transcribe(source,{})
        self.assertEqual(grid[0][2],Fraction(9,100))
        boundary=next(si for si,s in enumerate(document.sections)if dict(s.directives).get('BPM')=='180')
        self.assertEqual(next(t for si,_,t in grid if si==boundary),Fraction(17,20))
        self.assertEqual(duration(document),duration(source))
        self.assertEqual([m['beat_offset']for m in proof['measures']],['0','3/2','0'])
        self.assertTrue(all(b[2]>a[2]for a,b in zip(grid,grid[1:])))

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

    def test_targets_outside_the_template_remain_explicit_failures(self):
        points={(0,'head'):[-1.01,-.99],(1,'head'):[5.,5.01]}
        _,_,rows,failed,_=transcribe(template(),points)
        self.assertEqual(rows,{})
        self.assertEqual(set(failed),set(points))
