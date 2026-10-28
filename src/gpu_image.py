"""D3D11 GPU ROI/color conversion; download only the selected BGRA rectangle."""
import ctypes
from pathlib import Path
import platform
from PIL import Image
from architecture import process_architecture


class GPUImageConverter:
    def __init__(self):
        arch = process_architecture()
        if platform.system() != 'Windows' or arch not in ('amd64', 'arm64'):
            raise NotImplementedError('D3D11 image conversion requires Windows AMD64 or ARM64')
        try:
            self.dll = ctypes.CDLL(str(Path(__file__).parent / f'assets/gpu_roi_{arch}.dll'))
        except OSError as error:
            raise RuntimeError('D3D11 image conversion helper could not be loaded') from error
        ptr, uint = ctypes.c_void_p, ctypes.c_uint
        self.dll.ac_roi_open.argtypes = [ptr, uint, uint, ctypes.POINTER(ptr)]
        self.dll.ac_roi_open.restype = ctypes.c_int32
        self.dll.ac_roi_convert.argtypes = [ptr, ptr, uint, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, ptr, ctypes.c_size_t]
        self.dll.ac_roi_convert.restype = ctypes.c_int32
        self.dll.ac_roi_open_cpu.argtypes = [uint, uint, uint, uint, ctypes.POINTER(ptr)]
        self.dll.ac_roi_open_cpu.restype = ctypes.c_int32
        self.dll.ac_roi_convert_cpu.argtypes = self.dll.ac_roi_convert.argtypes
        self.dll.ac_roi_convert_cpu.restype = ctypes.c_int32
        self.dll.ac_roi_close.argtypes = [ptr]
        self.dll.ac_roi_close.restype = None
        self.handle = ptr()
        self.key = None
        self.buffer = None

    @staticmethod
    def check(result):
        if result < 0:
            raise RuntimeError(f'D3D11 image conversion failed: HRESULT 0x{result & 0xffffffff:08x}')

    def convert(self, frame, *, region=None, reference_size=None):
        from media import image_geometry
        angle, width, height, box = image_geometry(frame, region, reference_size)
        hardware = frame.format.name == 'd3d11'
        # Current hardware helper supports SDR BT.601/709, not HDR/BT.2020.
        if frame.colorspace not in (0, 1, 2, 5, 6) or frame.color_trc in (16, 18):
            raise NotImplementedError('GPU color conversion does not support this color space')
        x0, y0, x1, y1 = box or (0, 0, width, height)
        # PIL rotation is counter-clockwise; map display ROI back to source pixels.
        angle %= 360
        if angle == 90:
            x0, y0, x1, y1 = frame.width-y1, x0, frame.width-y0, x1
        elif angle == 180:
            x0, y0, x1, y1 = frame.width-x1, frame.height-y1, frame.width-x0, frame.height-y0
        elif angle == 270:
            x0, y0, x1, y1 = y0, frame.height-x1, y1, frame.height-x0
        size = x1-x0, y1-y0
        if min(size) <= 0 or x0 < 0 or y0 < 0 or x1 > frame.width or y1 > frame.height:
            raise ValueError('Image region is outside the video frame')
        key = (hardware, frame.width, frame.height, size)
        if key != self.key:
            self.close()
            if hardware:
                self.check(self.dll.ac_roi_open(frame.planes[0].buffer_ptr, *size, ctypes.byref(self.handle)))
            else:
                if frame.width % 2 or frame.height % 2:
                    raise NotImplementedError('GPU upload requires even frame dimensions')
                self.check(self.dll.ac_roi_open_cpu(frame.width, frame.height, *size, ctypes.byref(self.handle)))
            self.buffer = ctypes.create_string_buffer(size[0]*size[1]*4)
            self.key = key
        if hardware:
            convert = self.dll.ac_roi_convert
            texture, slice_index = frame.planes[0].buffer_ptr, frame.planes[1].buffer_ptr
        else:
            # Repack selected YUV frames only; RGB conversion/cropping stays on GPU.
            nv12 = frame.reformat(format='nv12')
            data = b''.join(memoryview(plane)[row*plane.line_size:row*plane.line_size+frame.width]
                            for plane in nv12.planes for row in range(plane.height))
            upload = ctypes.create_string_buffer(data)
            texture, slice_index = ctypes.cast(upload, ctypes.c_void_p), frame.width
            convert = self.dll.ac_roi_convert_cpu
        self.check(convert(self.handle, texture, slice_index, x0, y0,
                                          frame.colorspace == 1, frame.color_range == 2,
                                          self.buffer, len(self.buffer)))
        # GPU already produced RGB channels; Pillow only unpacks BGRA byte layout.
        image = Image.frombytes('RGB', size, self.buffer.raw, 'raw', 'BGRX')
        return image.rotate(angle, expand=True) if angle else image

    def close(self):
        if self.handle:
            self.dll.ac_roi_close(self.handle)
            self.handle = ctypes.c_void_p()
        self.buffer = None
        self.key = None
