"""Only positive near-receptor structure can make popup ownership uncertain."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.detector import SkinDetector
from piu_timeline.play.skins.held import BodyAtReceptor
from tests.play.skins.test_detector import examples


class ReceptorBodyTest(unittest.TestCase):
    def test_remote_tiles_and_short_or_disconnected_fragments_do_not_defer_inputs(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);examples(root)
            layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]}
            candidate=BodyAtReceptor(SkinDetector(load_bank(root/'bank.json'),layout,200,300))
            def body(top):
                return {'lane':0,'role':'hold_body','template':'hold_body','classification_status':'full_pattern',
                        'bounds_pixels':[16,top,24,top+12],'alternatives':[]}
            self.assertFalse(candidate([body(180)]))
            self.assertFalse(candidate([body(26)]))
            self.assertFalse(candidate([body(26),body(50),body(58)]))
            self.assertTrue(candidate([body(26),body(34),body(42)]))
            representative=body(26);representative['alternatives']=[body(34),body(42)]
            self.assertTrue(candidate([representative]))
            for p in representative['alternatives']:p['classification_status']='cap_only'
            self.assertFalse(candidate([representative]))

    def test_a_verified_endpoint_connection_at_the_receptor_is_local_hold_evidence(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);examples(root)
            layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1}for i in range(5)]}
            candidate=BodyAtReceptor(SkinDetector(load_bank(root/'bank.json'),layout,200,300))
            endpoint={'lane':0,'role':'hold_end','template_role':'hold_end','template':'hold_end',
                      'classification_status':'full_pattern','bounds_pixels':[10,10,30,45],'alternatives':[]}
            self.assertTrue(candidate([endpoint]))
            tile={'lane':0,'role':'hold_body','template':'hold_body','classification_status':'full_pattern',
                  'bounds_pixels':[10,20,18,32],'alternatives':[]}
            connection=candidate.explain([endpoint,tile])
            self.assertTrue(any(c['kind']=='cap_connection'and c['image_indices']==[0]for c in connection))
            self.assertTrue(any(c['kind']=='body_run'for c in connection))
            self.assertEqual(candidate.explain([endpoint,tile]),connection)
            failed=deepcopy(endpoint);failed.update(role='unknown',classification_status='cap_only')
            self.assertFalse(candidate([failed]))
            distant=deepcopy(endpoint);distant['bounds_pixels']=[10,100,30,135]
            self.assertFalse(candidate([distant]))
