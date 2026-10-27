"""Parallel images preserve frame identity, bounded memory and error semantics."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from piu_timeline.play.skins.bank import load_bank
from piu_timeline.play.skins.pipeline import classified_frames,worker_count
from tests.play.skins.test_detector import examples


class FramePipelineTest(unittest.TestCase):
    def fixture(self,root):
        items,_=examples(root);bank=load_bank(root/'bank.json')
        layout={'receptor_y':.05,'lanes':[{'x':.1+i*.1,'color':'blue'}for i in range(5)]}
        frames=[]
        for index,t in enumerate((1.,1.017,1.051,1.068)):
            image=np.zeros((300,200,3),dtype='uint8');top=40+20*index
            image[top:top+40,10:30]=items[0][1]
            frames.append((t+30,t,image))
        return bank,layout,frames

    def test_parallel_and_serial_detection_keep_identical_images_pts_order_and_roles(self):
        with tempfile.TemporaryDirectory()as tmp:
            bank,layout,frames=self.fixture(Path(tmp));original=[f[2].copy()for f in frames]
            serial=list(classified_frames(iter(frames),bank,layout,200,300,jobs=1))
            parallel=list(classified_frames(iter(frames),bank,layout,200,300,jobs=2))
            for index,(before,after)in enumerate(zip(serial,parallel,strict=True)):
                self.assertEqual(before[:2],after[:2])
                self.assertIs(after[2],frames[index][2])
                np.testing.assert_array_equal(after[2],original[index])
                self.assertEqual(json.dumps(before[3],sort_keys=True),json.dumps(after[3],sort_keys=True))
                tap=next(o for o in after[3]if o['role']=='tap')
                self.assertAlmostEqual(tap['y']*300,60+20*index)

    def test_prefetch_is_bounded_and_early_close_releases_the_input(self):
        with tempfile.TemporaryDirectory()as tmp:
            bank,layout,frames=self.fixture(Path(tmp));state={'read':0,'closed':False}
            def source():
                try:
                    for i in range(100):
                        state['read']+=1;yield frames[i%4]
                finally:state['closed']=True
            output=classified_frames(source(),bank,layout,200,300,jobs=2)
            next(output)
            self.assertLessEqual(state['read'],4)
            output.close()
            self.assertTrue(state['closed'])

    def test_worker_errors_propagate_without_draining_or_leaking_source_acquisition(self):
        with tempfile.TemporaryDirectory()as tmp:
            bank,layout,frames=self.fixture(Path(tmp))
            for jobs in (1,2):
                state={'read':0,'closed':False}
                def source():
                    try:
                        for i in range(100):
                            state['read']+=1
                            yield (31.,1.,np.zeros((2,2,3),dtype='uint8'))if i==0 else frames[i%4]
                    finally:state['closed']=True
                with self.subTest(jobs=jobs),self.assertRaisesRegex(ValueError,'differs from its geometry'):
                    list(classified_frames(source(),bank,layout,200,300,jobs=jobs))
                self.assertTrue(state['closed'])
                self.assertLessEqual(state['read'],2*jobs)

    def test_legacy_frames_do_not_start_workers_or_require_skin_settings(self):
        image=np.zeros((2,2,3),dtype='uint8')
        with patch.dict('os.environ',{'PIU_SKIN_JOBS':'invalid'}):
            rows=list(classified_frames(iter([(31.,1.,image)]),None,{},2,2))
            self.assertIs(rows[0][2],image)
            self.assertIsNone(rows[0][3])
            with self.assertRaises(ValueError):worker_count()
