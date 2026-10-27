"""Reviewed simultaneous cells must survive rebuilding in the same timing row."""
import unittest

from piu_timeline.charts.ucs import parse
from piu_timeline.charts.assertions import validate


class ChartAssertionsTest(unittest.TestCase):
    def document(self,rows):
        return parse(':Format=1\n:Mode=Single\n:BPM=120\n:Delay=0\n:Beat=4\n:Split=1\n'+rows)

    def fact(self):
        return {'id':'reviewed-chord','start_seconds':0,'end_seconds':1,
                'cells':{'0':'X','1':'X'},'reason':'Both panels require the same input time.'}

    def test_two_separate_rows_cannot_satisfy_a_reviewed_chord(self):
        validate(self.document('XX...\n.....\n'),[self.fact()])
        with self.assertRaisesRegex(ValueError,'reviewed-chord failed'):
            validate(self.document('X....\n.X...\n'),[self.fact()])

    def test_invalid_or_out_of_scope_assertions_are_rejected(self):
        for field,value in [('start_seconds',float('nan')),('end_seconds',0),
                            ('cells',{'5':'X'}),('cells',{'0':'?'}),('reason','')]:
            fact=self.fact();fact[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                validate(self.document('XX...\n'),[fact])
        with self.assertRaises(ValueError):validate(self.document('XX...\n'),[self.fact(),self.fact()])
