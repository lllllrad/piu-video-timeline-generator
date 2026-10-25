import io
import tempfile
from pathlib import Path
from hashlib import sha256
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock

import cv2
import numpy as np

from piu_timeline import paddle_ocr as paddle


class PaddleOCRTest(unittest.TestCase):
    def test_known_text_region_bypasses_detector_without_changing_pixels(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'digits.png';cv2.imwrite(str(path),np.zeros((24,48,3),dtype='uint8'))
            before=path.read_bytes()
            with patch.object(paddle,'recognizer',return_value=(None,[])), \
                    patch.object(paddle,'recognize_crops',return_value=[('15',.99)]), \
                    patch.object(paddle,'detect_boxes',side_effect=AssertionError('known region')):
                result=paddle.read_image(path,english=True,single_line=True)
            self.assertEqual(result[0]['text'],'15')
            self.assertEqual(result[0]['box'],[0,0,1,1])
            self.assertEqual(path.read_bytes(),before)

    def test_ctc_repeats_blanks_unicode_and_confidence(self):
        indices=[0,1,1,0,1,2,2,0]
        probabilities=np.full((len(indices),3),.01,dtype='float32')
        for row,index in enumerate(indices):probabilities[row,index]=.98
        text,confidence=paddle.decode_ctc(probabilities,['','탠','닉'])
        self.assertEqual(text,'탠탠닉')
        self.assertAlmostEqual(confidence,.98,places=5)
        self.assertEqual(paddle.decode_ctc(np.array([[1.,0,0]]),['','a','b']),('',0.))

    def test_official_bgr_normalization_padding_and_long_text(self):
        image=np.zeros((24,50,3),dtype='uint8');image[:,:,0]=255
        tensor=paddle.prepare_crop(image)
        self.assertEqual(tensor.shape,(1,3,48,320))
        np.testing.assert_array_equal(tensor[0,0,:,:100],1)
        np.testing.assert_array_equal(tensor[0,1:,:,:100],-1)
        np.testing.assert_array_equal(tensor[:,:,:,100:],0)
        self.assertEqual(paddle.prepare_crop(np.zeros((48,600,3),dtype='uint8')).shape,(1,3,48,600))

    def test_device_selection_requires_explicit_cuda_but_auto_falls_back(self):
        self.assertEqual(paddle.providers('auto',['CPUExecutionProvider']),['CPUExecutionProvider'])
        self.assertEqual(paddle.providers('cuda:2',['CUDAExecutionProvider'])[0],('CUDAExecutionProvider',{'device_id':2}))
        with self.assertRaises(ValueError):paddle.providers('cuda',['CPUExecutionProvider'])
        with self.assertRaises(ValueError):paddle.providers('mps',['CPUExecutionProvider'])

    def test_model_downloads_are_verified_atomic_and_reused(self):
        contents={'inference.onnx':b'model','inference.yml':b'config'}
        entry={'name':'example','revision':'pinned',**{k:sha256(v).hexdigest() for k,v in contents.items()}}
        def response(url,**kwargs):return io.BytesIO(contents[url.rsplit('/',1)[1]])
        with tempfile.TemporaryDirectory() as temporary,patch.object(paddle,'ROOT',Path(temporary)), \
                patch.dict(paddle.MODELS,{'test':entry}),patch.object(paddle.urllib.request,'urlopen',side_effect=response) as download:
            directory=paddle.model_files('test')
            self.assertEqual(download.call_count,2)
            paddle.model_files('test');self.assertEqual(download.call_count,2)
            (directory/'inference.onnx').write_bytes(b'corrupt')
            paddle.model_files('test');self.assertEqual(download.call_count,3)
            self.assertEqual((directory/'inference.onnx').read_bytes(),b'model')
            self.assertEqual(list(directory.glob('*.part')),[])

    def test_boxes_remain_in_original_coordinates_and_input_is_unchanged(self):
        session=Mock();session.get_inputs.return_value=[SimpleNamespace(name='x')]
        session.run.return_value=[np.array([[[.01,.98,.01],[.98,.01,.01],[.01,.01,.98]]]*2)]
        boxes=[[[0,3],[20,3],[20,15],[0,15]],[[30,3],[48,4],[47,15],[31,14]]]
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'image.png';cv2.imwrite(str(path),np.zeros((20,50,3),dtype='uint8'))
            before=path.read_bytes()
            with patch.object(paddle,'recognizer',return_value=(session,['','가','나'])),patch.object(paddle,'detect_boxes',return_value=boxes):
                lines=paddle.read_image(path)
            self.assertEqual([line['text'] for line in lines],['가나','가나'])
            self.assertEqual(lines[0]['box'],[0.,.15,.4,.6])
            for line in lines:
                x,y,w,h=line['box'];self.assertTrue(0<=x<x+w<=1 and 0<=y<y+h<=1)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(session.run.call_count,1)

    def test_detector_rescales_and_expands_only_confident_text_regions(self):
        probabilities=np.zeros((1,1,80,160),dtype='float32')
        probabilities[0,0,25:40,50:100]=.95
        probabilities[0,0,5:15,5:30]=.4
        session=Mock();session.get_inputs.return_value=[SimpleNamespace(name='x')]
        session.run.return_value=[probabilities]
        with patch.object(paddle,'detector',return_value=session):
            boxes=paddle.detect_boxes(np.zeros((160,320,3),dtype='uint8'),'cpu')
        self.assertEqual(len(boxes),1)
        box=boxes[0]
        self.assertLess(float(box[:,0].min()),100)
        self.assertGreater(float(box[:,0].max()),198)
        self.assertTrue(np.all((box[:,0]>=0)&(box[:,0]<=320)))
        self.assertTrue(np.all((box[:,1]>=0)&(box[:,1]<=160)))
        tensor=session.run.call_args.args[1]['x']
        self.assertEqual(tensor.shape,(1,3,480,960))


if __name__=='__main__':unittest.main()
