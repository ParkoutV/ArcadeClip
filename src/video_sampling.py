"""PTS-based video sampling and optional GPU decoding fallback."""
from i18n import tr
from concurrent.futures import CancelledError
from time import perf_counter
from contextlib import ExitStack
import gc
import av
from media import oriented_image
from analysis_common import check_cancel

def video_duration(container):
    if not container.streams.video:
        raise ValueError(tr('영상 스트림을 찾을 수 없습니다.'))
    stream = container.streams.video[0]
    return (float(stream.duration * stream.time_base) if stream.duration is not None
            else container.duration / av.time_base if container.duration is not None else None)


def clamp_analysis_end(path, start, end):
    with av.open(str(path)) as container:
        duration = video_duration(container)
    end = min(end, duration) if duration is not None else end
    if start >= end:
        raise ValueError(tr('영상 길이 안에서 구간을 선택해 주세요.'))
    return end


def samples(path, start, end, interval, cancel, *, decoder_threads=1, metrics=None, gpu=False,
            region=None, reference_size=None, on_frame=None, gpu_convert=None, pipelined=False):
    try:
        yield from _samples(path, start, end, interval, cancel, decoder_threads=decoder_threads,
                            metrics=metrics, gpu=gpu, region=region,
                            reference_size=reference_size, on_frame=on_frame,
                            gpu_convert=gpu_convert, pipelined=pipelined)
    finally:
        # After generator frames unwind, reclaim metadata cycles. Live frames
        # deliberately retained by a reference consumer remain reachable.
        gc.collect()


def _samples(path, start, end, interval, cancel, *, decoder_threads=1, metrics=None, gpu=False,
             region=None, reference_size=None, on_frame=None, gpu_convert=None, pipelined=False):
    gpu_convert = gpu if gpu_convert is None else gpu_convert
    hardware = None
    if gpu:
        from av.codec.hwaccel import HWAccel
        hardware = HWAccel("d3d11va", allow_software_fallback=False, is_hw_owned=True)
    with ExitStack() as resources:
        converter = None
        if gpu_convert:
            from gpu_image import GPUImageConverter
            converter = GPUImageConverter()
            resources.callback(converter.close)
        container = resources.enter_context(av.open(str(path), **({"hwaccel": hardware} if hardware else {})))
        if not container.streams.video:
            raise ValueError(tr('영상 스트림을 찾을 수 없습니다.'))
        stream = container.streams.video[0]
        stream.thread_type = "AUTO" if decoder_threads > 1 else "SLICE"
        stream.codec_context.thread_count = decoder_threads
        origin = stream.start_time or 0
        duration = video_duration(container)
        if duration is not None:
            end = min(end, duration)
        if start >= end:
            return
        container.seek(origin + int(start / stream.time_base), stream=stream, backward=True)
        selected = _selected(container, stream, origin, start, end, interval, cancel, metrics, on_frame)
        if pipelined:
            from pipeline import prefetch
            selected = prefetch(selected, cancel, capacity=2)
        resources.callback(selected.close)
        for seconds, frame in selected:
            began = perf_counter()
            if converter:
                image = converter.convert(frame, region=region, reference_size=reference_size)
            else:
                if frame.format.name == 'd3d11':
                    frame = frame.reformat(format='nv12')
                image = oriented_image(frame, region=region, reference_size=reference_size)
            if metrics is not None:
                metrics['convert_s'] += perf_counter() - began
                metrics['sample_frames'] += 1
                metrics['converter'] = 'GPU · D3D11 ROI→RGB' if converter else 'CPU'
            frame = None
            yield seconds, image
            del image


def _selected(container, stream, origin, start, end, interval, cancel, metrics, on_frame):
        target = start
        iterator = iter(container.decode(stream))
        while True:
            check_cancel(cancel)
            began = perf_counter()
            try:
                frame = next(iterator)
            except StopIteration:
                break
            if metrics is not None:
                metrics["decode_s"] += perf_counter() - began
                metrics["decoded_frames"] += 1
            check_cancel(cancel)
            if metrics is not None:
                metrics["decoder"] = "GPU · D3D11VA" if stream.codec_context.is_hwaccel else "CPU"
            if frame.pts is None:
                frame = None
                continue
            seconds = float((frame.pts - origin) * stream.time_base)
            if seconds >= end:
                break
            if on_frame is not None:
                on_frame(seconds, frame)
            if seconds + 1e-7 < target:
                frame = None
                continue
            yield seconds, frame
            frame = None
            target = seconds + interval


def analysis_samples(path, start, end, interval, cancel, threads, metrics, gpu, report, warnings,
                     *, region=None, reference_size=None, on_frame=None, gpu_convert=None, pipelined=False):
    # Resume at the next sampling target if the experimental decoder fails mid-stream.
    resume = start
    if gpu or gpu_convert:
        try:
            for seconds, image in samples(path, start, end, interval, cancel,
                                          decoder_threads=threads, metrics=metrics, gpu=gpu,
                                          gpu_convert=gpu_convert, pipelined=pipelined,
                                          region=region, reference_size=reference_size, on_frame=on_frame):
                resume = seconds + interval
                yield seconds, image
            return
        except CancelledError:
            raise
        except (av.FFmpegError, RuntimeError, ValueError, NotImplementedError) as error:
            message = tr('GPU 처리를 사용할 수 없어 CPU로 계속합니다: {error}', error=error)
            warnings.append(message)
            report(message)
    yield from samples(path, resume, end, interval, cancel, decoder_threads=threads, metrics=metrics,
                       region=region, reference_size=reference_size, on_frame=on_frame, pipelined=pipelined)
