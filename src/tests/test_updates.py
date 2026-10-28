"""Release lookup and report link: version comparison, response handling, and what is sent."""
import hashlib
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import zipfile

import updates


class FakeResponse:
    def __init__(self, payload, url='https://api.github.com/repos/x/y/releases/latest'):
        self.body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.url = url
        self.headers = {'Content-Length': str(len(self.body))}
        self._offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def geturl(self):
        return self.url

    def read(self, limit=None):
        if limit is None:
            return self.body
        chunk = self.body[self._offset:self._offset + limit]
        self._offset += len(chunk)
        return chunk


class VersionTests(unittest.TestCase):
    def test_version_matches_the_project_metadata(self):
        project = Path(updates.__file__).resolve().parents[1] / 'pyproject.toml'
        declared = tomllib.loads(project.read_text(encoding='utf-8'))['project']['version']
        self.assertEqual(updates.VERSION, declared)

    def test_newer_tags_are_recognised_regardless_of_prefix_or_suffix(self):
        for tag in ('0.1.1', 'v0.2.0', '1.0.0', '0.2.0-beta'):
            self.assertTrue(updates.is_newer(tag, '0.1.0'), tag)
        for tag in ('0.1.0', 'v0.1.0', '0.0.9', '0.1', ''):
            self.assertFalse(updates.is_newer(tag, '0.1.0'), tag)
        # A release without any leading number must not be read as an update.
        self.assertFalse(updates.is_newer('nightly', '0.1.0'))


class LookupTests(unittest.TestCase):
    def test_tag_is_returned_from_the_release_payload(self):
        with patch.object(updates.urllib.request, 'urlopen',
                          return_value=FakeResponse({'tag_name': 'v0.2.0'})):
            self.assertEqual(updates.latest_release(), 'v0.2.0')

    def test_plain_http_and_empty_tags_are_rejected(self):
        with patch.object(updates.urllib.request, 'urlopen',
                          return_value=FakeResponse({'tag_name': 'v9'}, url='http://example.invalid/')):
            with self.assertRaises(ValueError):
                updates.latest_release()
        with patch.object(updates.urllib.request, 'urlopen',
                          return_value=FakeResponse({'tag_name': '  '})):
            with self.assertRaises(ValueError):
                updates.latest_release()

    def test_lookup_targets_the_published_repository_over_https(self):
        self.assertTrue(updates.RELEASES_API.startswith('https://api.github.com/repos/'))
        for url in (updates.RELEASES_API, updates.RELEASES_PAGE, updates.NEW_ISSUE):
            self.assertIn(updates.REPOSITORY, url)
            self.assertTrue(url.startswith('https://'))


class MissingReleaseTests(unittest.TestCase):
    def test_a_draft_release_reads_as_nothing_published_not_a_failure(self):
        import urllib.error
        missing = urllib.error.HTTPError(updates.RELEASES_API, 404, 'Not Found', {}, None)
        with patch.object(updates.urllib.request, 'urlopen', side_effect=missing):
            self.assertIsNone(updates.latest_release())

    def test_other_http_errors_still_raise(self):
        import urllib.error
        refused = urllib.error.HTTPError(updates.RELEASES_API, 403, 'rate limited', {}, None)
        with patch.object(updates.urllib.request, 'urlopen', side_effect=refused):
            with self.assertRaises(urllib.error.HTTPError):
                updates.latest_release()


class SelfUpdateTests(unittest.TestCase):
    def test_latest_release_info_selects_matching_architecture_installer(self):
        payload = {
            'tag_name': 'v0.3.0',
            'html_url': 'https://github.com/151net/ArcadeClip/releases/tag/v0.3.0',
            'assets': [
                {
                    'name': 'ArcadeClip-0.3.0-windows-x64-setup.exe',
                    'browser_download_url': 'https://github.com/151net/ArcadeClip/releases/download/v0.3.0/ArcadeClip-0.3.0-windows-x64-setup.exe',
                },
                {
                    'name': 'ArcadeClip-0.3.0-windows-arm64-user-setup.exe',
                    'browser_download_url': 'https://github.com/151net/ArcadeClip/releases/download/v0.3.0/ArcadeClip-0.3.0-windows-arm64-user-setup.exe',
                },
                {
                    'name': 'ArcadeClip-0.3.0-windows-arm64-user-setup.exe.sha256',
                    'browser_download_url': 'https://github.com/151net/ArcadeClip/releases/download/v0.3.0/ArcadeClip-0.3.0-windows-arm64-user-setup.exe.sha256',
                },
            ],
        }
        with patch.object(updates.urllib.request, 'urlopen', return_value=FakeResponse(payload)):
            info = updates.latest_release_info(arch='ARM64')
        self.assertEqual(info['tag'], 'v0.3.0')
        self.assertEqual(info['installer_name'], 'ArcadeClip-0.3.0-windows-arm64-user-setup.exe')
        self.assertTrue(info['sha256_url'].endswith('.sha256'))

    def test_download_installer_and_prepare_local_update_exe_and_zip(self):
        fake_exe = b'MZ' + b'\x00' * 128
        expected_hash = hashlib.sha256(fake_exe).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_root = root / 'app'
            (app_root / 'src').mkdir(parents=True)
            with patch.object(
                updates.urllib.request,
                'urlopen',
                return_value=FakeResponse(fake_exe, url='https://example.com/ArcadeClip-setup.exe'),
            ):
                downloaded = updates.download_installer(
                    'https://example.com/ArcadeClip-setup.exe',
                    root / 'updates',
                    expected_sha256=expected_hash,
                )
            self.assertTrue(downloaded.is_file())
            exe_res = updates.prepare_local_update(downloaded, app_root=app_root)
            self.assertEqual(exe_res['mode'], 'installer')
            self.assertIn('/SILENT', exe_res['args'])

            zip_path = root / 'patch.zip'
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('src/updates_marker.py', 'UPDATED = True\n')
            zip_res = updates.prepare_local_update(zip_path, app_root=app_root)
            self.assertEqual(zip_res['mode'], 'zip')
            self.assertEqual(zip_res['updated_files'], 1)
            self.assertTrue((app_root / 'src' / 'updates_marker.py').is_file())


class ReportTests(unittest.TestCase):
    def test_report_link_opens_the_projects_own_form(self):
        url = updates.report_url()
        self.assertTrue(url.startswith(updates.NEW_ISSUE + '?'))
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query['template'], [updates.TEMPLATE])
        # The form asks its own questions; nothing about this machine rides along.
        self.assertEqual(set(query), {'template'})
        for leaked in ('debug.log', 'crash.log', 'C:' + chr(92), '/Users/'):
            self.assertNotIn(leaked, url)

    def test_the_form_the_link_names_is_in_the_repository(self):
        template = Path(__file__).resolve().parents[2] / '.github/ISSUE_TEMPLATE' / updates.TEMPLATE
        self.assertTrue(template.is_file(), template)
