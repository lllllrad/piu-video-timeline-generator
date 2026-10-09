import os
import sys
import unittest
from unittest.mock import patch, MagicMock

from piu_timeline import ocr


class OCRBackendTest(unittest.TestCase):
    def test_defaults_follow_host_and_linux_defaults_to_cpu(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "platform", "linux"):
            self.assertEqual(ocr.configuration(), {"backend": "easyocr", "device": "cpu"})
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
            ocr.reader(True, "cuda:0")
            self.assertEqual(fake.Reader.call_args.args, (["en"],))
            self.assertEqual(fake.Reader.call_args.kwargs["gpu"], "cuda:0")
        ocr.reader.cache_clear()
