import os
import sys
import tempfile
import warnings
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

from piu_timeline.vision import ocr


class OCRBackendTest(unittest.TestCase):
    def test_defaults_follow_host_and_linux_selects_device_automatically(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "platform", "linux"):
            self.assertEqual(ocr.configuration(), {"backend": "paddleocr", "device": "auto"})
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "platform", "darwin"):
            self.assertEqual(ocr.configuration(), {"backend": "vision", "device": "native"})

    def test_explicit_gpu_and_invalid_configuration(self):
        with patch.dict(os.environ, {"PIU_OCR_BACKEND": "easyocr", "PIU_OCR_DEVICE": "cuda:1"}):
            self.assertEqual(ocr.configuration()["device"], "cuda:1")
        with patch.dict(os.environ, {"PIU_OCR_BACKEND": "typo"}):
            with self.assertRaises(ValueError):
                ocr.configuration()

    def test_normalized_boxes_match_vision_contract(self):
        line = ocr.normalized_line([[10, 20], [50, 18], [52, 40], [9, 42]], "Song", .9, 100, 200)
        self.assertEqual(line["box"], [.09, .09, .43, .12])
        self.assertEqual(line["text"], "Song")

    def test_empty_batch_does_not_initialize_an_engine(self):
        with patch.object(ocr, "reader") as reader:
            self.assertEqual(ocr.ocr_images([]), [])
            reader.assert_not_called()


class EasyOCRAdapterTest(unittest.TestCase):
    def test_reader_reuse_language_device_and_local_models(self):
        fake = MagicMock()
        ocr.reader.cache_clear()
        with patch.dict(sys.modules, {"easyocr": fake}):
            first = ocr.reader(False, "cpu")
            self.assertIs(first, ocr.reader(False, "cpu"))
            fake.Reader.assert_called_once()
            args, kwargs = fake.Reader.call_args
            self.assertEqual(args, (["ko", "en"],))
            self.assertFalse(kwargs["gpu"])
            self.assertIn(".local/cache/easyocr", kwargs["model_storage_directory"])
            ocr.reader(False, "auto")
            self.assertIs(fake.Reader.call_args.kwargs["gpu"], True)
            ocr.reader(True, "cuda:0")
            self.assertEqual(fake.Reader.call_args.args, (["en"],))
            self.assertEqual(fake.Reader.call_args.kwargs["gpu"], "cuda:0")
        ocr.reader.cache_clear()

    def test_cpu_pinning_notice_is_scoped_and_other_warnings_remain_visible(self):
        from PIL import Image

        notice = ("'pin_memory' argument is set as true but no accelerator is found, "
                  "then device pinned memory won't be used.")

        def emit_notice():
            warnings.warn_explicit(notice, UserWarning, "dataloader.py", 1,
                                   module="torch.utils.data.dataloader")

        def readtext(*args, **kwargs):
            emit_notice()
            warnings.warn("Other OCR warning", UserWarning)
            return [([[0, 0], [10, 0], [10, 10], [0, 10]], "Song", .9)]

        engine = MagicMock()
        engine.readtext.side_effect = readtext
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.png"
            Image.new("RGB", (20, 20)).save(path)
            with patch.object(ocr, "configuration", return_value={"backend": "easyocr", "device": "auto"}), \
                    patch.object(ocr, "reader", return_value=engine), \
                    warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = ocr.ocr_images([path])
                self.assertEqual([str(item.message) for item in caught], ["Other OCR warning"])
                self.assertEqual(result[0]["lines"][0]["text"], "Song")
                emit_notice()
                self.assertEqual(str(caught[-1].message), notice)

class OCRContentCacheTest(unittest.TestCase):
    def setUp(self):
        ocr._IMAGE_CACHE.clear()
        self.addCleanup(ocr._IMAGE_CACHE.clear)

    def test_model_pipeline_identity_invalidates_same_image_content(self):
        from piu_timeline.vision import paddle as paddle_ocr
        with tempfile.TemporaryDirectory() as temporary:
            image=Path(temporary)/'image.png';image.write_bytes(b'identical pixels')
            result=[{'path':str(image),'lines':[]}]
            with patch.object(ocr,'configuration',return_value={'backend':'paddleocr','device':'cpu'}), \
                    patch.object(ocr,'_ocr_images_uncached',return_value=result) as infer:
                ocr.ocr_images([image]);ocr.ocr_images([image])
                self.assertEqual(infer.call_count,1)
                with patch.object(paddle_ocr,'PIPELINE',{'schema':1,'models':{'new':'weights'}}):
                    ocr.ocr_images([image])
                self.assertEqual(infer.call_count,2)

    def test_known_line_inference_does_not_reuse_detection_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            image=Path(temporary)/'line.png';image.write_bytes(b'same encoded image')
            with patch.object(ocr,'_ocr_images_uncached',return_value=[{'lines':[]}]) as infer:
                ocr.ocr_images([image],english=True)
                ocr.ocr_images([image],english=True,single_line=True)
                self.assertEqual(infer.call_count,2)
                self.assertTrue(infer.call_args.kwargs['single_line'])
                ocr.ocr_images([image],english=True,single_line=True)
                self.assertEqual(infer.call_count,2)

    def test_content_language_and_changed_pixels_are_independent(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "first.png", Path(temporary) / "second.png"
            first.write_bytes(b"same encoded pixels")
            second.write_bytes(first.read_bytes())
            def infer(paths, english=False):
                return [{"path": str(p), "lines": [{"text": "English" if english else "Korean",
                                                   "box": [0, 0, 1, 1]}]} for p in paths]
            with patch.object(ocr, "_ocr_images_uncached", side_effect=infer) as engine:
                result = ocr.ocr_images([first, second])
                self.assertEqual(engine.call_count, 1)
                self.assertEqual(len(engine.call_args.args[0]), 1)
                self.assertEqual([r["path"] for r in result], [str(first), str(second)])
                result[0]["lines"][0]["text"] = "mutated"
                self.assertEqual(ocr.ocr_images([first])[0]["lines"][0]["text"], "Korean")
                self.assertEqual(ocr.ocr_images([second], english=True)[0]["lines"][0]["text"], "English")
                second.write_bytes(b"changed pixels")
                ocr.ocr_images([second])
                self.assertEqual(engine.call_count, 3)
