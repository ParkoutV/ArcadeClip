"""Native PP-OCRv5 line recognition using ONNX Runtime, NumPy and Pillow.

The pinned model contains its character dictionary. Detection, polygon clipping
and text-box visualization are unnecessary for the app's user-supplied ROIs.
"""
import math

import numpy as np


def resize_linear(pixels, width, height):
    """Half-pixel bilinear resize, without a downsampling antialias filter.

    This preserves the preprocessing used to train the model while avoiding
    OpenCV's native extension dependency on Windows ARM64.
    """
    source_height, source_width = pixels.shape[:2]
    x = np.maximum((np.arange(width) + .5) * source_width / width - .5, 0)
    y = np.maximum((np.arange(height) + .5) * source_height / height - .5, 0)
    x0, y0 = x.astype(int), y.astype(int)
    x1, y1 = np.minimum(x0 + 1, source_width - 1), np.minimum(y0 + 1, source_height - 1)
    wx = (x - x0)[None, :, None]
    wy = (y - y0)[:, None, None]
    top = pixels[y0[:, None], x0] * (1 - wx) + pixels[y0[:, None], x1] * wx
    bottom = pixels[y1[:, None], x0] * (1 - wx) + pixels[y1[:, None], x1] * wx
    return np.rint(top * (1 - wy) + bottom * wy).astype(np.float32)


def prepare_image(image):
    """Produce BGR, NCHW float32 input with the model's 48px line height."""
    image = image.convert('RGB')
    if image.width == 0 or image.height == 0:
        raise ValueError('OCR image must not be empty.')
    width = max(320, int(48 * image.width / image.height))
    resized_width = min(width, math.ceil(48 * image.width / image.height))
    pixels = resize_linear(np.asarray(image), resized_width, 48)
    tensor = np.zeros((1, 3, 48, width), dtype=np.float32)
    tensor[0, :, :, :resized_width] = (pixels[:, :, ::-1].transpose(2, 0, 1) / 127.5) - 1
    return tensor


def decode_ctc(predictions, characters):
    if predictions.ndim != 3 or predictions.shape[0] != 1 or predictions.shape[2] != len(characters):
        raise ValueError('OCR model output does not match its character dictionary.')
    indices = predictions[0].argmax(axis=1)
    scores = predictions[0].max(axis=1)
    selected = indices != 0
    selected[1:] &= indices[1:] != indices[:-1]
    if not selected.any():
        return '', 0.0
    return ''.join(characters[index] for index in indices[selected]), float(scores[selected].mean())


class OnnxRecognizer:
    def __init__(self, model):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self.session = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])
        dictionary = self.session.get_modelmeta().custom_metadata_map.get('character')
        if not dictionary:
            raise ValueError('OCR model is missing its character dictionary.')
        self.characters = ['', *dictionary.splitlines(), ' ']
        self.input_name = self.session.get_inputs()[0].name

    def __call__(self, image):
        output = self.session.run(None, {self.input_name: prepare_image(image)})[0]
        return decode_ctc(output, self.characters)
