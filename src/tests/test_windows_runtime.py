"""Architecture selection and optional external runtime regressions."""
import configparser
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import architecture
import runtime_config
import sources
import updates
import ocr_bridge


class ArchitectureTests(unittest.TestCase):
    def test_native_dll_follows_interpreter_even_under_emulation(self):
        for machine, arch in ((0x8664, 'amd64'), (0xaa64, 'arm64'), (0x14c, None)):
            pe = bytearray(256)
            pe[:2] = b'MZ'
            struct.pack_into('<I', pe, 0x3c, 128)
            pe[128:132] = b'PE\0\0'
            struct.pack_into('<H', pe, 132, machine)
            with self.subTest(machine=machine), patch('architecture.sys.platform', 'win32'), \
                 patch('builtins.open', return_value=io.BytesIO(pe)), \
                 patch('architecture.platform.machine', return_value='ARM64'):
                self.assertEqual(architecture.process_architecture(), arch)

    def test_specific_update_preferred_for_both_architectures(self):
        names = ['ArcadeClip-windows-arm64-setup.exe', 'ArcadeClip-windows-amd64-setup.exe',
                 'ArcadeClip-windows-universal-user-setup.exe']
        payload = {'tag_name': 'v0.2.3', 'assets': [
            {'name': n, 'browser_download_url': 'https://example.test/' + n}
            for n in [*names, *(name + '.sha256' for name in names)]]}
        for arch in ('AMD64', 'x86_64', 'ARM64', 'aarch64'):
            with self.subTest(arch=arch), patch('updates._fetch_release_payload', return_value=payload):
                result = updates.latest_release_info(arch=arch)
                self.assertEqual(result['installer_name'], names[0] if arch in ('ARM64', 'aarch64') else names[1])
                self.assertTrue(result['sha256_url'].endswith('.sha256'))

    def test_legacy_universal_update_remains_a_fallback(self):
        name = 'ArcadeClip-windows-universal-user-setup.exe'
        with patch('updates._fetch_release_payload', return_value={
                'tag_name': 'v1', 'assets': [{'name': name, 'browser_download_url': 'https://example.test/' + name}]}):
            for arch in ('ARM64', 'AMD64'):
                self.assertEqual(updates.latest_release_info(arch=arch)['installer_name'], name)

    def test_never_falls_back_to_wrong_architecture_or_unknown_exe(self):
        for arch, name in (('ARM64', 'ArcadeClip-windows-x64-setup.exe'),
                           ('AMD64', 'ArcadeClip-windows-arm64-setup.exe'),
                           ('AMD64', 'ArcadeClip-windows-x86-setup.exe'),
                           ('x86', 'ArcadeClip-windows-universal-setup.exe')):
            with self.subTest(arch=arch, name=name), patch('updates._fetch_release_payload', return_value={
                    'tag_name': 'v1', 'assets': [{'name': name, 'browser_download_url': 'https://example.test/' + name}]}):
                self.assertIsNone(updates.latest_release_info(arch=arch)['installer_url'])


class RuntimeTests(unittest.TestCase):
    def test_native_ocr_does_not_require_a_worker_but_legacy_bundles_do(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / 'portable-runtime.json'
            with patch.object(ocr_bridge, '__file__', str(root / 'src/ocr_bridge.py')):
                manifest.write_text(json.dumps({'ocr_backend': 'native-onnx'}))
                self.assertIsNone(ocr_bridge.bundled_worker())
                manifest.write_text(json.dumps({'ocr_python': 'ocr-runtime/python.exe'}))
                with self.assertRaisesRegex(RuntimeError, 'missing'):
                    ocr_bridge.bundled_worker()
                (root / 'ocr-runtime').mkdir()
                python = root / 'ocr-runtime/python.exe'
                python.touch()
                self.assertEqual(ocr_bridge.bundled_worker(), python.resolve())

    def test_configured_ffmpeg_uses_unicode_path_and_does_not_affect_deno(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / '사용자 도구 % ffmpeg'
            tools.mkdir()
            for name in ('ffmpeg.exe', 'ffprobe.exe'):
                (tools / name).touch()
            config = configparser.ConfigParser(interpolation=None)
            config['Runtime'] = {'Python': '', 'FFmpegDir': str(tools)}
            with (root / 'runtime-config.ini').open('w', encoding='utf-16') as output:
                config.write(output)
            with patch.object(runtime_config, 'ROOT', root):
                self.assertEqual(sources.find_tool('ffmpeg'), str(tools / 'ffmpeg.exe'))
                self.assertEqual(sources.find_tool('ffprobe'), str(tools / 'ffprobe.exe'))
                self.assertIsNone(runtime_config.configured_tool('deno'))
                (tools / 'ffmpeg.exe').unlink()
                with self.assertRaisesRegex(RuntimeError, 'Setup'):
                    sources.find_tool('ffmpeg')

    def test_absent_config_and_bundled_selection_use_normal_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(runtime_config, 'ROOT', root):
                self.assertIsNone(runtime_config.configured_tool('ffmpeg'))
                (root / 'runtime-config.ini').write_text('[Runtime]\nPython=\nFFmpegDir=\n', encoding='utf-16')
                self.assertIsNone(runtime_config.configured_tool('ffmpeg'))
