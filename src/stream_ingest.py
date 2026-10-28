"""OBS stream-key ingest (direct RTMP/SRT with LTE grace period or YouTube live watch) and auto-clipping."""
from collections import deque
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import threading
import time
from urllib.parse import urlsplit
import uuid

from i18n import tr
from sources import (
    _command,
    _media_duration,
    ffmpeg_https_args,
    find_tool,
    run_command,
    youtube_url,
)
from tool_errors import ToolError


def analyze(*args, **kwargs):
    from recognition import analyze as _analyze
    return _analyze(*args, **kwargs)


def export_clips(*args, **kwargs):
    from export import export_clips as _export_clips
    return _export_clips(*args, **kwargs)


def generate_stream_key() -> str:
    return "ac-" + "-".join(secrets.token_hex(2) for _ in range(3))


def validate_stream_key(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(tr('스트림 키는 영문·숫자·하이픈(-)으로 4–64자를 입력해 주세요.'))
    cleaned = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", cleaned):
        raise ValueError(tr('스트림 키는 영문·숫자·하이픈(-)으로 4–64자를 입력해 주세요.'))
    return cleaned


def validate_host(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(tr('고정 주소(DDNS 또는 IP) 형식을 확인해 주세요.'))
    cleaned = value.strip()
    if not cleaned:
        return "127.0.0.1"
    if (not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", cleaned)
            or ".." in cleaned or cleaned[0] in ".-" or cleaned[-1] in ".-"):
        raise ValueError(tr('고정 주소(DDNS 또는 IP) 형식을 확인해 주세요.'))
    return cleaned


def local_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            ip = probe.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"


def obs_connection_info(protocol: str, host: str, port: int, stream_key: str) -> dict:
    if protocol not in ("rtmp", "srt"):
        raise ValueError(tr('지원하지 않는 스트림 프로토콜입니다.'))
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError(tr('포트 번호는 1–65535 사이로 지정해 주세요.'))
    host = validate_host(host)
    key = validate_stream_key(stream_key)
    if protocol == "rtmp":
        server_url = f"rtmp://{host}:{port}/live2"
        listen_url = f"rtmp://0.0.0.0:{port}/live2/{key}"
    else:
        # Give the sender time to deliver the 2.5s latency queue when it closes.
        server_url = f"srt://{host}:{port}?streamid={key}&latency=2500000&linger=5"
        listen_url = f"srt://0.0.0.0:{port}?mode=listener&streamid={key}&latency=2500000"
    return {
        "protocol": protocol,
        "host": host,
        "port": port,
        "stream_key": key,
        "server_url": server_url,
        "listen_url": listen_url,
    }


def port_forwarding_guide(protocol: str = "rtmp", port: int = 1935,
                          host: str = "", stream_key: str = "") -> str:
    lan_ip = local_lan_ip()
    transport = "TCP" if protocol == "rtmp" else "UDP"
    key = stream_key.strip() if isinstance(stream_key, str) and stream_key.strip() else "ac-xxxx-xxxx-xxxx"
    display_host = host.strip() if isinstance(host, str) and host.strip() else "myarcade.iptime.org"
    try:
        info = obs_connection_info(protocol if protocol in ("rtmp", "srt") else "rtmp",
                                   display_host, port if type(port) is int and 1 <= port <= 65535 else 1935, key)
        server_url = info["server_url"]
        key = info["stream_key"]
    except ValueError:
        server_url = f"rtmp://{display_host}:{port}/live2"
    return tr(
        '[선택지 A · 직접 스트림 수신을 위한 포트포워딩 및 고정 DDNS 가이드]\n\n'
        '외부망(오락실 PC)에서 이 PC로 직접 스트림을 보내려면 공유기 포트포워딩과 고정 DDNS 주소가 필요합니다.\n'
        '(만약 공유기 설정이 어려운 휴대용 핫스팟 환경이라면 [방식 B: YouTube 라이브 자동 감지]를 선택하세요.)\n\n'
        '■ 현재 이 PC의 네트워크 정보\n'
        '• 내부 IP 주소 (포트포워딩 대상): {lan_ip}\n'
        '• 개방할 프로토콜 및 포트: {transport} {port}번\n\n'
        '■ STEP 1. 고정 DDNS 주소 발급 (공인 IP가 바뀌어도 주소 고정)\n'
        '1) ipTIME 공유기 사용 시:\n'
        '   • 브라우저에서 http://192.168.0.1 접속 → [고급 설정] → [특수기능] → [DDNS 설정]\n'
        '   • 호스트 이름(예: myarcade.iptime.org)과 사용자 ID(이메일) 입력 후 [추가] 클릭\n'
        '2) 통신사 공유기(KT·SKB·LGU+) 또는 일반 공유기 사용 시:\n'
        '   • 무료 DDNS 서비스인 DuckDNS(https://www.duckdns.org) 또는 No-IP에서 무료 도메인 발급\n'
        '   • 발급받은 도메인 주소를 이 프로그램의 [고정 주소 (DDNS/IP)] 칸에 입력\n\n'
        '■ STEP 2. 공유기 포트포워딩 설정\n'
        '1) 공유기 설정 페이지 접속 → [고급 설정] → [NAT/라우터 관리] → [포트포워드 설정]\n'
        '2) 새 규칙 추가:\n'
        '   • 내부 IP 주소: {lan_ip}\n'
        '   • 프로토콜: {transport}\n'
        '   • 외부 포트: {port} ~ {port} / 내부 포트: {port} ~ {port}\n\n'
        '■ STEP 3. 오락실 OBS (추가 스트림) 입력값\n'
        '• 서버(Server): {server_url}\n'
        '• 스트림 키(Stream Key): {key}\n'
        '• 한 번만 등록해 두면 오락실에서 스트림 소스를 켜고 끌 때마다 자동으로 원본 저장 및 클립 추출이 진행됩니다.',
        lan_ip=lan_ip,
        transport=transport,
        port=port,
        server_url=server_url,
        key=key,
    )


def youtube_stream_target(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(tr('YouTube 라이브 또는 채널 주소(@핸들/live)를 입력해 주세요.'))
    text = value.strip()
    if text.startswith("@") and re.fullmatch(r"@[A-Za-z0-9_.-]{2,60}", text):
        return f"https://www.youtube.com/{text}/live"
    try:
        return youtube_url(text)
    except ValueError:
        pass
    try:
        parsed = urlsplit(text)
        if (parsed.scheme not in {"https", "http"} or parsed.username
                or parsed.password or parsed.port not in {None, 80, 443}):
            raise ValueError
        host = (parsed.hostname or "").lower()
        if host not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            raise ValueError
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) in (1, 2) and parts[0].startswith("@") and re.fullmatch(r"@[A-Za-z0-9_.-]{2,60}", parts[0]):
            if len(parts) == 2 and parts[1] not in {"live", "streams"}:
                raise ValueError
            return f"https://www.youtube.com/{parts[0]}/live"
        if len(parts) in (2, 3) and parts[0] == "channel" and re.fullmatch(r"UC[A-Za-z0-9_-]{20,30}", parts[1]):
            if len(parts) == 3 and parts[2] not in {"live", "streams"}:
                raise ValueError
            return f"https://www.youtube.com/channel/{parts[1]}/live"
    except (ValueError, AttributeError):
        pass
    raise ValueError(tr('YouTube 라이브 또는 채널 주소(@핸들/live)를 입력해 주세요.'))


def is_individual_youtube_live_url(value: str) -> bool:
    """Return True if value is an individual YouTube broadcast/video link rather than a channel live URL."""
    try:
        youtube_url(value)
        return True
    except ValueError:
        return False


def _finish_recording(process):
    """Ask FFmpeg to flush muxer buffers before bounded forced termination."""
    if process.poll() is not None:
        return
    try:
        process.stdin.write('q\n')
        process.stdin.flush()
        process.wait(timeout=3)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # This is FFmpeg itself, with no child downloader. Keep termination bounded
        # even when taskkill is unavailable in a restricted Windows environment.
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def _record_part(args, part_path, cancel, report, *, idle_timeout=None,
                 stop_event=None, stall_timeout=30):
    if cancel.is_set():
        raise InterruptedError(tr('작업을 취소했습니다.'))
    if stop_event is not None and stop_event.is_set():
        return False
    options = ({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
               if os.name == "nt" else {"start_new_session": True})
    errors = deque(maxlen=30)
    stopped = False
    with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, text=True, encoding="utf-8",
                          errors="replace", **options) as process:
        def read_stderr():
            for raw in process.stderr:
                line = raw.strip()
                if line.startswith('out_time_us='):
                    try:
                        elapsed = max(0, int(line.partition('=')[2]) / 1000000)
                    except ValueError:
                        continue
                    report(tr('실시간 스트림 수신 및 저장 중 · {elapsed:.1f}초', elapsed=elapsed))
                elif line and not re.match(r'^[a-z_0-9]+=.*$', line):
                    errors.append(line)
        reader = threading.Thread(target=read_stderr, daemon=True)
        reader.start()
        began = last_data = time.monotonic()
        previous_size = 0
        try:
            while process.poll() is None:
                if cancel.is_set():
                    raise InterruptedError(tr('작업을 취소했습니다.'))
                now = time.monotonic()
                size = part_path.stat().st_size if part_path.is_file() else 0
                if size > previous_size:
                    last_data, previous_size = now, size
                if stop_event is not None and stop_event.is_set():
                    stopped = True
                    _finish_recording(process)
                    break
                if ((not size and idle_timeout is not None and now - began >= idle_timeout)
                        or (size and now - last_data >= stall_timeout)):
                    stopped = True
                    _finish_recording(process)
                    break
                try:
                    process.wait(timeout=.2)
                except subprocess.TimeoutExpired:
                    pass
        except BaseException:
            _finish_recording(process)
            raise
        finally:
            reader.join()
    recorded = part_path.is_file() and part_path.stat().st_size > 0
    if process.returncode and not stopped:
        error = ToolError('\n'.join(errors), process.returncode)
        # A disconnected publisher often exits FFmpeg nonzero after usable media.
        output_error = re.search(r'error (?:muxing|writing|submitting|closing)|av_interleaved_write_frame',
                                 '\n'.join(errors), re.IGNORECASE)
        if not recorded or error.kind in {'disk_full', 'permission'} or output_error:
            if output_error:
                error.capture_output_error = True
            raise error
        report(tr('스트림 연결이 끊겼습니다. 저장된 영상은 유지하고 재연결을 확인합니다.'))
    return recorded


def _listen_part(ffmpeg: str, info: dict, part_path: Path, cancel: threading.Event,
                 report, *, idle_timeout: float | None = None,
                 stop_event: threading.Event | None = None) -> bool:
    args = [ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-nostats', '-progress', 'pipe:2']
    if info['protocol'] == 'rtmp':
        args += ['-listen', '1', '-f', 'flv', '-i', info['listen_url']]
    else:
        args += ['-i', info['listen_url']]
    args += ['-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy',
             '-flush_packets', '1', '-f', 'mpegts', str(part_path)]
    return _record_part(args, part_path, cancel, report,
                        idle_timeout=idle_timeout, stop_event=stop_event)


def receive_direct_stream(protocol: str, port: int, stream_key: str, directory: Path,
                          cancel: threading.Event, report, *, host: str = "127.0.0.1",
                          grace_seconds: int = 60, max_empty_retries: int = 3,
                          stop_event: threading.Event | None = None) -> Path:
    """Receive an OBS stream via RTMP/SRT, coalescing LTE reconnects within grace_seconds."""
    if type(grace_seconds) is not int or not 0 <= grace_seconds <= 600:
        raise ValueError(tr('재연결 대기 시간은 0–600초 사이로 지정해 주세요.'))
    info = obs_connection_info(protocol, host, port, stream_key)
    ffmpeg = find_tool("ffmpeg")
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    # Keep received media recoverable if validation, merging, or disk I/O fails.
    work = directory / ('.stream-' + uuid.uuid4().hex)
    work.mkdir()
    parts: list[Path] = []
    empty_attempts = 0
    report(tr('OBS 스트림 수신 대기 중 · {url} (스트림 키: {key})',
              url=info["server_url"], key=info["stream_key"]))
    while not parts:
        if cancel.is_set():
            raise InterruptedError(tr('작업을 취소했습니다.'))
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError(tr('수신된 스트림 영상이 없어 작업을 종료했습니다.'))
        part = work / "part_001.ts"
        listen_kwargs = {"stop_event": stop_event} if stop_event is not None else {}
        if _listen_part(ffmpeg, info, part, cancel, report, **listen_kwargs):
            parts.append(part)
            break
        part.unlink(missing_ok=True)
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError(tr('수신된 스트림 영상이 없어 작업을 종료했습니다.'))
        empty_attempts += 1
        if max_empty_retries > 0 and empty_attempts >= max_empty_retries:
            raise RuntimeError(tr('스트림 연결을 확인하지 못했습니다. 포트포워딩과 스트림 키를 확인해 주세요.'))

    while grace_seconds > 0 and not cancel.is_set() and not (stop_event is not None and stop_event.is_set()):
        next_index = len(parts) + 1
        next_part = work / f"part_{next_index:03d}.ts"
        report(tr('스트림 신호 끊김 · {seconds}초 동안 재연결을 대기합니다 (LTE 일시 끊김 보호)…',
                  seconds=grace_seconds))
        listen_kwargs = {"idle_timeout": grace_seconds}
        if stop_event is not None:
            listen_kwargs["stop_event"] = stop_event
        if _listen_part(ffmpeg, info, next_part, cancel, report, **listen_kwargs):
            parts.append(next_part)
        else:
            next_part.unlink(missing_ok=True)
            break

    if cancel.is_set():
        raise InterruptedError(tr('작업을 취소했습니다.'))

    final_path = work / "stream.ts"
    if len(parts) == 1:
        parts[0].rename(final_path)
    else:
        report(tr('재연결된 스트림 조각 {count}개를 하나로 합치고 있습니다…', count=len(parts)))
        concat_file = work / "concat.txt"
        concat_file.write_text(
            "\n".join("file '" + part.name.replace("'", "'\\''") + "'" for part in parts) + "\n",
            encoding="utf-8",
        )
        run_command(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat",
             "-safe", "0", "-i", str(concat_file), "-c", "copy", str(final_path)],
            cancel,
            report,
            cwd=work,
        )

    actual_duration = _media_duration(final_path)
    if not math.isfinite(actual_duration) or actual_duration <= 0:
        raise RuntimeError(tr('수신한 스트림 영상의 길이를 확인할 수 없습니다.'))
    metadata = {
        "title": f"OBS {protocol.upper()} Stream",
        "uploader": "OBS",
        "video_date": datetime.now().astimezone().strftime(tr('%Y-%m-%d %H시')),
        "protocol": protocol,
        "parts_count": len(parts),
        "local_duration": actual_duration,
        "is_live": True,
    }
    (work / "source.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    for part in parts:
        part.unlink(missing_ok=True)
    (work / 'concat.txt').unlink(missing_ok=True)
    destination = directory / ("stream-" + uuid.uuid4().hex)
    work.rename(destination)
    saved_path = destination / final_path.name
    report(tr('OBS 스트림 저장 완료 · {path}', path=saved_path))
    return saved_path



def _inspect_youtube_live(target, cancel, report):
    # Resolve the live edge only: no DVR probes and no finite download sections.
    try:
        output = run_command(_command() + ['--no-live-from-start', '--skip-download',
                             '--format', 'b/bv*+ba', '--dump-single-json', '--', target], cancel, report)
    except ToolError as error:
        if (not is_individual_youtube_live_url(target)
                and 'the channel is not currently live' in error.detail.lower()):
            return {'live_status': 'is_upcoming'}
        raise
    data = json.loads(output)
    if not isinstance(data, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', str(data.get('id', ''))):
        raise ValueError(tr('개별 라이브 방송 정보를 확인할 수 없습니다.'))
    return data


def _youtube_live_inputs(data):
    formats = [f for f in data.get('formats', [])
               if f.get('protocol') in ('m3u8', 'm3u8_native')
               and f.get('url', '').startswith('https://') and not f.get('has_drm')]
    videos = [f for f in formats if f.get('vcodec') not in (None, 'none', 'images')]
    # Muxed HLS preserves A/V timing and avoids independently moving live edges.
    muxed = [f for f in videos if f.get('acodec') not in (None, 'none')]
    if not videos:
        raise ValueError(tr('실시간 수신 가능한 HLS 영상 형식을 찾지 못했습니다.'))
    video = max(muxed or videos, key=lambda f: (f.get('height') or 0, f.get('fps') or 0, f.get('tbr') or 0))
    selected = [video]
    if not muxed:
        audio = next((f for f in reversed(formats) if f.get('vcodec') == 'none'
                      and f.get('acodec') != 'none'), None)
        if audio is not None:
            selected.append(audio)
    return selected


def _receive_youtube_part(data, part, cancel, report, stop_event):
    formats = _youtube_live_inputs(data)
    args = [find_tool('ffmpeg'), '-y', '-hide_banner', '-loglevel', 'error', '-copyts',
            '-start_at_zero', '-nostats', '-progress', 'pipe:2']
    for fmt in formats:
        args += ['-rw_timeout', '15000000'] + ffmpeg_https_args()
        headers = fmt.get('http_headers') or data.get('http_headers') or {}
        if any('\r' in str(v) or '\n' in str(v) for pair in headers.items() for v in pair):
            raise ValueError(tr('영상 요청 헤더를 확인할 수 없습니다.'))
        if headers:
            args += ['-headers', ''.join(f'{k}: {v}\r\n' for k, v in headers.items())]
        args += ['-live_start_index', '-1', '-i', fmt['url']]
    args += ['-map', '0:v:0', '-map', '1:a:0' if len(formats) > 1 else '0:a:0?',
             '-c', 'copy', '-avoid_negative_ts', 'make_zero',
             '-flush_packets', '1', '-f', 'matroska', str(part)]
    return _record_part(args, part, cancel, report, idle_timeout=45, stop_event=stop_event)


def _wait_poll(cancel: threading.Event, stop_event: threading.Event | None, seconds: float) -> bool:
    """Sleep up to seconds; raise on cancel and return True immediately if stop_event is set."""
    if stop_event is None:
        if cancel.wait(seconds):
            raise InterruptedError(tr('작업을 취소했습니다.'))
        return False
    deadline = time.monotonic() + max(0.0, float(seconds))
    while True:
        if cancel.is_set():
            raise InterruptedError(tr('작업을 취소했습니다.'))
        if stop_event.is_set():
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        if cancel.wait(min(0.1, remaining)):
            raise InterruptedError(tr('작업을 취소했습니다.'))


def _ensure_part_duration(part: Path, cancel: threading.Event, report) -> float:
    try:
        duration = _media_duration(part)
        if math.isfinite(duration) and duration > 0:
            return duration
    except RuntimeError:
        pass
    remuxed = part.with_suffix(".remux" + part.suffix)
    try:
        run_command(
            [find_tool("ffmpeg"), "-y", "-v", "error", "-i", str(part),
             "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
             "-avoid_negative_ts", "make_zero", str(remuxed)],
            cancel,
            report,
        )
        if remuxed.is_file() and remuxed.stat().st_size > 0:
            os.replace(remuxed, part)
    except Exception:
        remuxed.unlink(missing_ok=True)
    return _media_duration(part)


def watch_youtube_stream(url: str, directory: Path, cancel: threading.Event, report, *,
                         poll_seconds: float = 15.0, workers: int = 4,
                         wait_for_end: bool = True, max_polls: int = 0,
                         stop_event: threading.Event | None = None,
                         from_start_click: bool = False) -> dict:
    """Record from the live edge until stop/end, refreshing URLs after a disconnect.

    Legacy range-download options are accepted for callers but never select DVR media.
    """
    target = youtube_stream_target(url)
    if type(workers) is not int or not 1 <= workers <= 16:
        raise ValueError(tr('동시 다운로드 수는 1–16개로 지정해 주세요.'))
    if not isinstance(poll_seconds, (int, float)) or not math.isfinite(poll_seconds) or not 1 <= poll_seconds <= 300:
        raise ValueError(tr('감지 주기는 1–300초 사이로 지정해 주세요.'))
    work = Path(directory).resolve() / ('youtube-live-' + uuid.uuid4().hex)
    parts, metadata = [], None
    polls = failures = 0
    last_error = None
    class LookupCancel:
        def is_set(self):
            return cancel.is_set() or (stop_event is not None and stop_event.is_set())
    while not (stop_event is not None and stop_event.is_set()):
        if cancel.is_set():
            raise InterruptedError(tr('작업을 취소했습니다.'))
        polls += 1
        report(tr('YouTube 라이브 연결을 확인하고 있습니다…'))
        try:
            data = _inspect_youtube_live(target, LookupCancel(), report)
            if not (data.get('is_live') or data.get('live_status') == 'is_live'):
                if metadata is not None:
                    break
                if data.get('live_status') != 'is_upcoming' and is_individual_youtube_live_url(target):
                    raise ValueError(tr('현재 진행 중인 YouTube 라이브 링크를 입력해 주세요.'))
                failures = 0
                report(tr('방송 시작 대기 중 · {seconds:g}초 후 다시 확인합니다…', seconds=poll_seconds))
            else:
                # Pin a channel URL to this broadcast so reconnects cannot switch sessions.
                target = youtube_url('https://www.youtube.com/watch?v=' + data['id'])
                metadata = {k: data.get(k) for k in ('id', 'title', 'uploader', 'live_status')}
                metadata.update(url=target, is_live=True, protocol='youtube_live',
                                video_date=datetime.now().astimezone().strftime(tr('%Y-%m-%d %H시')))
                work.mkdir(parents=True, exist_ok=True)
                part = work / f'part_{len(parts) + 1:04d}.mkv'
                report(tr('YouTube 라이브 실시간 수신을 시작합니다. 정지하거나 방송이 종료되면 클립을 생성합니다.'))
                try:
                    recorded = _receive_youtube_part(data, part, cancel, report, stop_event)
                finally:
                    # Retain partial recordings on errors/cancel; never delete received media.
                    if part.is_file() and part.stat().st_size > 0:
                        parts.append(part)
                if recorded:
                    failures = 0
                else:
                    failures += 1
                if stop_event is not None and stop_event.is_set():
                    break
                report(tr('라이브 연결을 다시 확인합니다. 저장된 영상은 유지됩니다.'))
        except InterruptedError:
            if not cancel.is_set() and stop_event is not None and stop_event.is_set():
                break
            raise
        except (ToolError, ValueError, OSError, RuntimeError) as error:
            last_error = error
            failures += 1
            report(str(error))
            if isinstance(error, ToolError) and (error.kind in {'disk_full', 'permission', 'tool_missing'}
                                                or getattr(error, 'capture_output_error', False)):
                raise
        if failures >= 3:
            if not parts:
                raise last_error or RuntimeError(tr('라이브 영상 수신을 시작하지 못했습니다.'))
            report(tr('재연결에 실패했습니다. 현재까지 저장된 영상으로 클립을 생성합니다.'))
            break
        if max_polls > 0 and polls >= max_polls:
            if parts:
                break
            raise last_error or RuntimeError(tr('진행 중인 YouTube 라이브 방송을 찾지 못했습니다.'))
        _wait_poll(cancel, stop_event, min(1., poll_seconds) if parts and not failures else poll_seconds)
    if cancel.is_set():
        raise InterruptedError(tr('작업을 취소했습니다.'))
    if not parts:
        raise RuntimeError(tr('수신된 YouTube 라이브 영상이 없어 작업을 종료했습니다.'))
    # Validate parts before merging; damaged files remain available for recovery.
    for part in parts:
        if _ensure_part_duration(part, cancel, report) <= 0:
            raise RuntimeError(tr('수신한 스트림 영상의 길이를 확인할 수 없습니다.'))
    final = work / 'stream.mkv'
    if len(parts) == 1:
        parts[0].rename(final)
    else:
        manifest = work / 'concat.txt'
        manifest.write_text(''.join(f"file '{p.name}'\n" for p in parts), encoding='utf-8')
        run_command([find_tool('ffmpeg'), '-y', '-v', 'error', '-f', 'concat', '-safe', '0',
                     '-i', str(manifest), '-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy', str(final)],
                    cancel, report)
    duration = _media_duration(final)
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(tr('수신한 스트림 영상의 길이를 확인할 수 없습니다.'))
    metadata.update(local_duration=duration, parts_count=len(parts), time_basis='live_capture')
    (work / 'source.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    for part in parts:
        part.unlink(missing_ok=True)
    (work / 'concat.txt').unlink(missing_ok=True)
    return dict(path=final, metadata=metadata, start=0., end=duration,
                stopped=stop_event is not None and stop_event.is_set())


def auto_clip_session(video_path: Path, profile: dict | None, directory: Path,
                      output_directory: Path | None, cancel: threading.Event, report, *,
                      start_offset: float = -10.0, end_offset: float = 10.0,
                      export_settings: dict | None = None, analysis_options: dict | None = None,
                      auto_export: bool = True) -> dict:
    """Analyze a recorded stream session and automatically export detected song clips."""
    video_path = Path(video_path).resolve()
    duration = _media_duration(video_path)
    outcome = {
        "path": video_path,
        "duration": duration,
        "analysis": None,
        "originals": [],
        "clips": [],
        "exported": {"saved": [], "failed": [], "cancelled": False},
    }
    if not auto_export or profile is None:
        return outcome

    options = dict(analysis_options or {})
    analysis = analyze(video_path, 0, duration, profile, directory, cancel, report, **options)
    outcome["analysis"] = analysis
    if analysis.get("cancelled"):
        outcome["exported"]["cancelled"] = True
        return outcome

    from clips import offset_bounds, validate_clip
    originals = []
    clips = []
    for raw in analysis.get("clips", []):
        row = dict(raw)
        row["clip_id"] = uuid.uuid4().hex
        originals.append(validate_clip(row))
        edited = dict(row)
        try:
            edited["start"], edited["end"] = offset_bounds(
                edited["start"], edited["end"], start_offset, end_offset, duration
            )
        except ValueError:
            pass
        has_song = bool(edited.get("song_id") or edited.get("image_url"))
        edited["selected"] = has_song
        clips.append(validate_clip(edited))

    if clips and not any(row.get("selected") for row in clips):
        for row in clips:
            row["selected"] = True

    outcome["originals"] = originals
    outcome["clips"] = clips

    selected = [row for row in clips if row.get("selected")]
    if selected and output_directory is not None:
        settings = {"mode": "fast"}
        if export_settings:
            settings.update(export_settings)
        outcome["exported"] = export_clips(selected, Path(output_directory), cancel, report, **settings)
    return outcome
