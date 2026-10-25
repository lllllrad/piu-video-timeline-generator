from fractions import Fraction
import unittest

from piu_timeline.charts.ucs import parse


TEMPLATE = ':Format=1\n:Mode=Single\n:BPM=120\n:Delay=90\n:Beat=4\n:Split=2\n.....\n.....\n:BPM=180\n:Delay=-10\n:Beat=3\n:Split=3\n.....\n.....\n'


class UcsTest(unittest.TestCase):
    def test_section_timing_and_roundtrip(self):
        doc = parse(TEMPLATE)
        times = [time for _, _, time in doc.grid()]
        self.assertEqual(times, [Fraction(9,100), Fraction(34,100), Fraction(58,100), Fraction(58,100)+Fraction(1,9)])
        self.assertEqual(parse(doc.text()), doc)

    def test_densification_preserves_original_rows_and_changes_lane_width(self):
        doc = parse(TEMPLATE)
        expanded = doc.expanded(10)
        self.assertEqual(expanded.mode, 'Double')
        self.assertTrue(all(len(row) == 10 for section in expanded.sections for row in section.rows))
        grid = list(expanded.grid())
        for si, ri, time in doc.grid():
            old = int(dict(doc.sections[si].directives)['Split'])
            new = int(dict(expanded.sections[si].directives)['Split'])
            self.assertIn((si, ri*(new//old), time), grid)
        self.assertEqual(parse(expanded.text()), expanded)

    def test_refuses_to_erase_existing_notes(self):
        with self.assertRaisesRegex(ValueError, 'empty timing template'):
            parse(TEMPLATE.replace('.....', 'X....', 1)).expanded(5)

    def test_rejects_unsupported_timing_and_invalid_notes(self):
        for text in (TEMPLATE.replace('BPM=120','BPM=0'), TEMPLATE.replace('Split=2','Split=1.5'),
                     TEMPLATE.replace('Beat=4','Beat=0'), TEMPLATE.replace('.....','....'),
                     TEMPLATE.replace('.....','Z....'), TEMPLATE.replace('BPM=120','BPM=nan'),
                     TEMPLATE+':Speed=2\n.....\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text)
