"""Image geometry uses the same scaled support and identity as acquisition."""
from pathlib import Path
import tempfile
import unittest

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.coverage import reference_rows,image_spans
from tests.play.skins.test_detector import examples


class ReferenceCoverageTest(unittest.TestCase):
    def test_alpha_padding_and_undeclared_rows_are_excluded_at_the_acquisition_scale(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);examples(root);bank=load_bank(root/'bank.json')
            layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]}
            data={'analysis_width':200,'analysis_height':300,'layout':layout,
                  'skin_detector':{'bank_path':str(root/'bank.json'),'contract':{'bank':bank['contract']}}}
            rows=reference_rows(data)
            self.assertEqual(rows['hold_start'],[[0,20],[22,35]])
            self.assertEqual(rows['hold_end'],[[0,12],[15,35]])
            self.assertEqual(image_spans({'template':'hold_start','bounds_pixels':[10,105,30,140]},rows),
                             [(105,125),(127,140)])
            data.update(analysis_width=400,analysis_height=600)
            scaled=reference_rows(data)
            self.assertEqual(scaled['hold_start'],[[0,40],[44,70]])
            self.assertEqual(scaled['hold_end'],[[0,24],[30,70]])
            data['skin_detector']['contract']['bank']={}
            with self.assertRaisesRegex(ValueError,'differ from the acquired'):
                reference_rows(data)
