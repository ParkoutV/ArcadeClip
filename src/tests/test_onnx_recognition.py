"""Model input and CTC decoding contracts, independent of model downloads."""
import unittest

import numpy as np
from PIL import Image

from onnx_recognition import decode_ctc, prepare_image, resize_linear


class NativeOCRTests(unittest.TestCase):
    def test_ctc_repeats_blanks_spaces_and_unicode(self):
        characters = ['', 'A', 'あ', ' ']
        tokens = [0, 1, 1, 0, 1, 2, 2, 3, 0]
        predictions = np.zeros((1, len(tokens), len(characters)), dtype=np.float32)
        for time, token in enumerate(tokens):
            predictions[0, time, token] = .9
        text, confidence = decode_ctc(predictions, characters)
        self.assertEqual(text, 'AAあ ')
        self.assertAlmostEqual(confidence, .9)

    def test_blank_output_and_wrong_dictionary(self):
        self.assertEqual(decode_ctc(np.ones((1, 3, 1)), ['']), ('', 0.0))
        with self.assertRaises(ValueError):
            decode_ctc(np.ones((1, 3, 2)), [''])

    def test_bgr_normalization_and_neutral_padding(self):
        tensor = prepare_image(Image.new('RGB', (48, 48), 'red'))
        self.assertEqual(tensor.shape, (1, 3, 48, 320))
        self.assertEqual(tensor.dtype, np.float32)
        np.testing.assert_array_equal(tensor[0, :, 0, 0], [-1, -1, 1])
        self.assertTrue(np.all(tensor[:, :, :, 48:] == 0))

    def test_wide_grayscale_and_empty_images(self):
        self.assertEqual(prepare_image(Image.new('L', (800, 48))).shape, (1, 3, 48, 800))
        with self.assertRaises(ValueError):
            prepare_image(Image.new('RGB', (0, 48)))

    def test_resize_uses_half_pixel_centres_and_clamps_edges(self):
        pixels = np.array([[[0, 0, 0], [100, 100, 100]]], dtype=np.uint8)
        np.testing.assert_array_equal(resize_linear(pixels, 4, 1)[0, :, 0], [0, 25, 75, 100])
        np.testing.assert_array_equal(resize_linear(pixels, 1, 1)[0, 0], [50, 50, 50])
