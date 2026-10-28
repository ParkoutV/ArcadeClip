"""Tests for OBS stream-key ingest (Option A direct RTMP/SRT and Option B YouTube live watch) and auto-clipping."""
import json
from pathlib import Path
import tempfile
import sys
import threading
import unittest
from unittest.mock import patch

import stream_ingest


class StreamIngestTests(unittest.TestCase):
    def test_stream_key_and_obs_connection_info(self):
        key = stream_ingest.generate_stream_key()
        self.assertRegex(key, r"^ac-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}$")
        self.assertEqual(stream_ingest.validate_stream_key(f"  {key}  "), key)

        for bad_key in ("", "ab", "bad key", "ac/../secret", "a" * 65, None):
            with self.assertRaises(ValueError):
                stream_ingest.validate_stream_key(bad_key)

        self.assertEqual(stream_ingest.validate_host(""), "127.0.0.1")
        self.assertEqual(stream_ingest.validate_host("myarcade.iptime.org"), "myarcade.iptime.org")
        for bad_host in ("http://example.com", "my..host.com", "-bad.host", "bad.host.", "a/b"):
            with self.assertRaises(ValueError):
                stream_ingest.validate_host(bad_host)

        rtmp = stream_ingest.obs_connection_info("rtmp", "myarcade.iptime.org", 1935, key)
        self.assertEqual(rtmp["server_url"], "rtmp://myarcade.iptime.org:1935/live2")
        self.assertEqual(rtmp["listen_url"], f"rtmp://0.0.0.0:1935/live2/{key}")

        srt = stream_ingest.obs_connection_info("srt", "myarcade.duckdns.org", 9000, key)
        self.assertEqual(
            srt["server_url"],
            f"srt://myarcade.duckdns.org:9000?streamid={key}&latency=2500000&linger=5",
        )
        self.assertEqual(
            srt["listen_url"],
            f"srt://0.0.0.0:9000?mode=listener&streamid={key}&latency=2500000",
        )

    def test_port_forwarding_and_ddns_guide_includes_network_details(self):
        with patch.object(stream_ingest, "local_lan_ip", return_value="192.168.0.42"):
            guide = stream_ingest.port_forwarding_guide(
                "rtmp", 1935, "myarcade.iptime.org", "ac-1234-5678-90ab"
            )
        self.assertIn("192.168.0.42", guide)
        self.assertIn("TCP", guide)
        self.assertIn("1935", guide)
        self.assertIn("DDNS", guide)
        self.assertIn("rtmp://myarcade.iptime.org:1935/live2", guide)
        self.assertIn("ac-1234-5678-90ab", guide)

    def test_youtube_stream_target_accepts_channels_and_videos(self):
        self.assertEqual(
            stream_ingest.youtube_stream_target("@arcade_player"),
            "https://www.youtube.com/@arcade_player/live",
        )
        self.assertEqual(
            stream_ingest.youtube_stream_target("https://www.youtube.com/@arcade_player/live"),
            "https://www.youtube.com/@arcade_player/live",
        )
        self.assertEqual(
            stream_ingest.youtube_stream_target(
                "https://www.youtube.com/channel/UC1234567890abcdefghijkl/live"
            ),
            "https://www.youtube.com/channel/UC1234567890abcdefghijkl/live",
        )
        self.assertEqual(
            stream_ingest.youtube_stream_target("https://youtu.be/abcdefghijk"),
            "https://www.youtube.com/watch?v=abcdefghijk",
        )
        for invalid in ("", "https://evil.com/@arcade/live", "https://www.youtube.com/playlist?list=1"):
            with self.assertRaises(ValueError):
                stream_ingest.youtube_stream_target(invalid)

    def test_receive_direct_stream_coalesces_lte_reconnect_parts(self):
        calls = []

        def fake_listen(ffmpeg, info, part_path, cancel, report, *, idle_timeout=None):
            calls.append((part_path.name, idle_timeout))
            if len(calls) in (1, 2):
                part_path.write_bytes(b"ts-segment-" + str(len(calls)).encode("ascii"))
                return True
            return False

        def fake_concat(args, cancel, report, *, cwd=None, **kwargs):
            output_path = Path(args[-1])
            output_path.write_bytes(b"merged-ts-stream")
            return ""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(stream_ingest, "find_tool", return_value="/tools/ffmpeg"), \
                    patch.object(stream_ingest, "_listen_part", side_effect=fake_listen), \
                    patch.object(stream_ingest, "run_command", side_effect=fake_concat) as run_cmd, \
                    patch.object(stream_ingest, "_media_duration", return_value=185.5):
                saved = stream_ingest.receive_direct_stream(
                    "srt", 9000, "ac-1111-2222-3333", root, threading.Event(), lambda _: None,
                    host="myarcade.duckdns.org", grace_seconds=45,
                )
            self.assertTrue(saved.is_file())
            self.assertEqual(saved.read_bytes(), b"merged-ts-stream")
            self.assertEqual(calls, [("part_001.ts", None), ("part_002.ts", 45), ("part_003.ts", 45)])
            run_cmd.assert_called_once()
            meta = json.loads((saved.parent / "source.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["parts_count"], 2)
            self.assertEqual(meta["protocol"], "srt")
            self.assertEqual(meta["local_duration"], 185.5)

    def test_live_capture_saves_before_stop_and_never_uses_dvr_download(self):
        stop = threading.Event()
        data = dict(id='abcdefghijk', title='Live', is_live=True)
        def receive(data, path, cancel, report, stop_event):
            self.assertFalse(stop.is_set())
            path.write_bytes(b'live video')
            stop.set()
            return True
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(stream_ingest, '_inspect_youtube_live', return_value=data), \
             patch.object(stream_ingest, '_receive_youtube_part', side_effect=receive) as capture, \
             patch.object(stream_ingest, '_media_duration', return_value=12), \
             patch('sources.download_section') as download, patch('sources.inspect_source') as inspect:
            result = stream_ingest.watch_youtube_stream('https://youtu.be/abcdefghijk', Path(tmp),
                       threading.Event(), lambda _: None, stop_event=stop)
            self.assertEqual(result['path'].read_bytes(), b'live video')
            self.assertTrue(result['stopped'])
            self.assertEqual(result['end'], 12)
            self.assertEqual(result['metadata']['time_basis'], 'live_capture')
            capture.assert_called_once()
            download.assert_not_called()
            inspect.assert_not_called()

    def test_live_capture_retries_metadata_errors_and_pins_channel(self):
        data = dict(id='abcdefghijk', is_live=True)
        stop = threading.Event()
        def receive(data, path, cancel, report, stop_event):
            path.write_bytes(b'video')
            stop.set()
            return True
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(stream_ingest, '_inspect_youtube_live', side_effect=[RuntimeError('temporary'), data]) as inspect, \
             patch.object(stream_ingest, '_receive_youtube_part', side_effect=receive), \
             patch.object(stream_ingest, '_media_duration', return_value=8), \
             patch.object(stream_ingest, '_wait_poll', return_value=False), \
             patch('sources.download_section') as download:
            messages = []
            result = stream_ingest.watch_youtube_stream('@arcade_player', Path(tmp), threading.Event(),
                       messages.append, stop_event=stop)
            self.assertEqual(inspect.call_count, 2)
            self.assertIn('temporary', messages)
            self.assertEqual(result['metadata']['url'], 'https://www.youtube.com/watch?v=abcdefghijk')
            download.assert_not_called()

    def test_live_capture_reconnects_without_treating_error_as_broadcast_end(self):
        data = dict(id='abcdefghijk', is_live=True)
        ended = dict(id='abcdefghijk', is_live=False, live_status='post_live')
        def receive(data, path, *args):
            path.write_bytes(b'video')
            return True
        def merge(args, *unused):
            Path(args[-1]).write_bytes(b'merged')
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(stream_ingest, '_inspect_youtube_live', side_effect=[data, RuntimeError('temporary'), data, ended]) as inspect, \
             patch.object(stream_ingest, '_receive_youtube_part', side_effect=receive) as capture, \
             patch.object(stream_ingest, '_media_duration', return_value=8), \
             patch.object(stream_ingest, '_wait_poll', return_value=False), \
             patch.object(stream_ingest, 'find_tool', return_value='ffmpeg'), \
             patch.object(stream_ingest, 'run_command', side_effect=merge):
            result = stream_ingest.watch_youtube_stream('@arcade_player', Path(tmp), threading.Event(), lambda _: None)
            self.assertEqual(capture.call_count, 2)
            self.assertEqual(inspect.call_count, 4)
            self.assertEqual(inspect.call_args_list[1].args[0], 'https://www.youtube.com/watch?v=abcdefghijk')
            self.assertEqual(result['metadata']['parts_count'], 2)
            self.assertEqual(result['path'].read_bytes(), b'merged')

    def test_live_capture_errors_are_reported_and_bounded(self):
        with patch.object(stream_ingest, '_inspect_youtube_live', side_effect=RuntimeError('access denied')) as inspect, \
             patch.object(stream_ingest, '_wait_poll', return_value=False):
            messages = []
            with self.assertRaisesRegex(RuntimeError, 'access denied'):
                stream_ingest.watch_youtube_stream('https://youtu.be/abcdefghijk', '.', threading.Event(), messages.append)
            self.assertEqual(inspect.call_count, 3)
            self.assertEqual(messages.count('access denied'), 3)

    def test_offline_channel_is_waiting_but_network_errors_are_not_hidden(self):
        with patch.object(stream_ingest, '_command', return_value=['yt-dlp']), \
             patch.object(stream_ingest, 'run_command', side_effect=stream_ingest.ToolError('The channel is not currently live')):
            data = stream_ingest._inspect_youtube_live('https://www.youtube.com/@arcade/live', threading.Event(), lambda _: None)
            self.assertEqual(data['live_status'], 'is_upcoming')
        with patch.object(stream_ingest, '_command', return_value=['yt-dlp']), \
             patch.object(stream_ingest, 'run_command', side_effect=stream_ingest.ToolError('HTTP error 403')):
            with self.assertRaises(stream_ingest.ToolError):
                stream_ingest._inspect_youtube_live('https://www.youtube.com/@arcade/live', threading.Event(), lambda _: None)

    def test_stop_during_reconnect_lookup_finalizes_received_media(self):
        stop = threading.Event()
        calls = []
        def inspect(target, cancel, report):
            calls.append(target)
            if len(calls) == 1:
                return dict(id='abcdefghijk', is_live=True)
            stop.set()
            self.assertTrue(cancel.is_set())
            raise InterruptedError('lookup stopped')
        def receive(data, path, *args):
            path.write_bytes(b'video')
            return True
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(stream_ingest, '_inspect_youtube_live', side_effect=inspect), \
             patch.object(stream_ingest, '_receive_youtube_part', side_effect=receive), \
             patch.object(stream_ingest, '_media_duration', return_value=8), \
             patch.object(stream_ingest, '_wait_poll', return_value=False):
            result = stream_ingest.watch_youtube_stream('https://youtu.be/abcdefghijk', Path(tmp),
                         threading.Event(), lambda _: None, stop_event=stop)
            self.assertTrue(result['stopped'])
            self.assertEqual(result['path'].read_bytes(), b'video')

    def test_live_ffmpeg_inputs_use_live_edge_headers_and_separate_audio(self):
        video = dict(protocol='m3u8_native', url='https://media.example/video', vcodec='h264', acodec='none', height=1080)
        audio = dict(protocol='m3u8_native', url='https://media.example/audio', vcodec='none', acodec='aac')
        data = dict(formats=[video, audio], http_headers={'User-Agent': 'test'})
        with patch.object(stream_ingest, 'find_tool', return_value='ffmpeg'), \
             patch.object(stream_ingest, '_record_part', return_value=True) as record:
            stream_ingest._receive_youtube_part(data, Path('live.mkv'), threading.Event(), lambda _: None, None)
            args = record.call_args.args[0]
            self.assertEqual(args.count('-live_start_index'), 2)
            self.assertIn('1:a:0', args)
            self.assertIn('User-Agent: test\r\n', args)
            self.assertNotIn('--live-from-start', args)
        muxed = {**video, 'height': 720, 'acodec': 'aac'}
        self.assertEqual(stream_ingest._youtube_live_inputs(dict(formats=[video, audio, muxed])), [muxed])

    def test_recorder_stall_flushes_with_q_and_retains_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'part.ts'
            marker = Path(tmp) / 'flushed'
            script = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b'media'); command=sys.stdin.readline(); pathlib.Path(sys.argv[2]).write_text(command)"
            self.assertTrue(stream_ingest._record_part(
                [sys.executable, '-c', script, str(path), str(marker)], path,
                threading.Event(), lambda _: None, stall_timeout=.1))
            self.assertEqual(marker.read_text(), 'q\n')
            self.assertEqual(path.read_bytes(), b'media')

    def test_recorder_initial_timeout_and_error_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'part.ts'
            self.assertFalse(stream_ingest._record_part(
                [sys.executable, '-c', 'import sys; sys.stdin.readline()'], path,
                threading.Event(), lambda _: None, idle_timeout=.1))
            with self.assertRaises(stream_ingest.ToolError) as caught:
                stream_ingest._record_part([sys.executable, '-c',
                    "import sys; print('HTTP error 403 https://example.com/?token=secret', file=sys.stderr); sys.exit(1)"],
                    path, threading.Event(), lambda _: None)
            self.assertEqual(caught.exception.kind, 'forbidden')
            self.assertNotIn('token=secret', caught.exception.detail)

    def test_auto_clip_session_analyzes_applies_offsets_and_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "stream.ts"
            video.write_bytes(b"stream")
            out_dir = root / "clips"
            profile = {
                "version": 1,
                "name": "Arcade",
                "size": [1920, 1080],
                "regions": {
                    "jacket": [0.1, 0.1, 0.3, 0.3],
                    "achievement": [0.4, 0.4, 0.6, 0.5],
                    "player": [0.4, 0.5, 0.6, 0.6],
                },
                "recognition": {},
            }
            fake_analysis = {
                "profile": profile,
                "warnings": [],
                "cancelled": False,
                "clips": [
                    {
                        "source": str(video),
                        "start": 20.0,
                        "end": 140.0,
                        "title": "Test Song",
                        "image_url": "song1.png",
                        "player": "PLAYER1",
                        "achievement": 100.5,
                        "reviewed": False,
                    }
                ],
            }
            with patch.object(stream_ingest, "_media_duration", return_value=200.0), \
                    patch.object(stream_ingest, "analyze", return_value=fake_analysis) as mock_analyze, \
                    patch.object(
                        stream_ingest, "export_clips",
                        return_value={"saved": [str(out_dir / "clip1.mp4")], "failed": [], "cancelled": False},
                    ) as mock_export:
                outcome = stream_ingest.auto_clip_session(
                    video, profile, root, out_dir, threading.Event(), lambda _: None,
                    start_offset=-5.0, end_offset=8.0, export_settings={"mode": "fast"},
                )
            mock_analyze.assert_called_once()
            mock_export.assert_called_once()
            exported_rows = mock_export.call_args.args[0]
            self.assertEqual(len(exported_rows), 1)
            self.assertAlmostEqual(exported_rows[0]["start"], 15.0)
            self.assertAlmostEqual(exported_rows[0]["end"], 148.0)
            self.assertEqual(len(outcome["exported"]["saved"]), 1)


if __name__ == "__main__":
    unittest.main()
