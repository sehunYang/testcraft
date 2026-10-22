import hashlib
import json
import tempfile
import threading
import time
from pathlib import Path
import urllib.request
import unittest
from unittest.mock import patch
import zipfile

from app import codex_setup, runtime


def _tempdir():
    return tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.runtime')


def _account(plan, *, account_type='chatgpt', requires_auth=True):
    account = {'type': account_type}
    if plan is not None:
        account['planType'] = plan
    return {'account': account, 'requiresOpenaiAuth': requires_auth}


class CodexSetupTests(unittest.TestCase):
    def test_paid_chatgpt_plans_are_accepted(self):
        for plan in ('plus', 'pro', 'team', 'business', 'enterprise', 'edu'):
            with self.subTest(plan=plan):
                result = codex_setup.derive_account_state(_account(plan), installed=True, version='1.2.3')
                self.assertTrue(result['ready'])
                self.assertTrue(result['authenticated'])
                self.assertEqual(result['plan'], plan)
                self.assertEqual(result['phase'], 'ready')

    def test_free_unknown_and_api_key_accounts_are_not_eligible(self):
        for plan in ('free', 'trial', 'unknown', None):
            with self.subTest(plan=plan):
                result = codex_setup.derive_account_state(_account(plan), installed=True)
                self.assertTrue(result['authenticated'])
                self.assertFalse(result['ready'])
        result = codex_setup.derive_account_state(_account('pro', account_type='apiKey'), installed=True)
        self.assertFalse(result['authenticated'])
        self.assertIsNone(result['plan'])
        self.assertFalse(result['ready'])
        result = codex_setup.derive_account_state(_account('pro', requires_auth=False), installed=True)
        self.assertFalse(result['ready'])

    def test_not_installed_status_is_not_ready(self):
        result = codex_setup.derive_account_state(_account('pro'), installed=False)
        self.assertFalse(result['installed'])
        self.assertFalse(result['ready'])
        self.assertEqual(result['phase'], 'missing')

    def test_public_status_contains_only_sanitized_fields(self):
        manager = codex_setup.CodexSetup()
        with patch.object(runtime, 'installed_mode', return_value=True), \
                patch.object(codex_setup, '_executable', return_value='codex.exe'), \
                patch.object(codex_setup, '_version', return_value='1.2.3'):
            with manager._lock:
                manager._phase = 'ready'
                manager._authenticated = True
                manager._plan = 'pro'
                manager._ready = True
                manager._last_check = time.monotonic()

            result = manager.status()

        self.assertEqual(result, {
            'required': True, 'installed': True, 'version': '1.2.3',
            'authenticated': True, 'plan': 'pro', 'ready': True,
            'phase': 'ready', 'error': None,
        })
        self.assertNotIn('token', json.dumps(result).lower())
        self.assertNotIn('account', result)
        self.assertNotIn('log', result)

    def test_account_check_uses_mock_app_server_and_drops_private_fields(self):
        manager = codex_setup.CodexSetup()

        class FakeClient:
            process = type('Process', (), {'poll': lambda self: None})()

            def request(self, method, params=None):
                self_outer.assertEqual(method, 'account/read')
                self_outer.assertEqual(params, {'refreshToken': False})
                return {
                    'account': {'type': 'chatgpt', 'email': 'teacher@example.com',
                                'planType': 'plus', 'accessToken': 'secret'},
                    'requiresOpenaiAuth': True,
                    'refreshToken': 'secret',
                }

            def close(self):
                pass

        self_outer = self
        with patch.object(codex_setup, '_executable', return_value='mock-codex.exe'), \
                patch.object(codex_setup, '_version', return_value='2.0.0'), \
                patch.object(manager, '_get_client', return_value=FakeClient()), \
                patch.object(runtime, 'installed_mode', return_value=True):
            manager._check_worker()
            result = manager.status()

        self.assertTrue(result['ready'])
        self.assertTrue(result['authenticated'])
        self.assertEqual(result['plan'], 'plus')
        self.assertNotIn('teacher@example.com', json.dumps(result))
        self.assertNotIn('secret', json.dumps(result))

    def test_chatgpt_login_completion_checks_plan_without_exposing_response(self):
        manager = codex_setup.CodexSetup()

        class FakeClient:
            process = type('Process', (), {'poll': lambda self: None})()

            def request(self, method, params=None):
                if method == 'account/login/start':
                    self_outer.assertEqual(params['type'], 'chatgpt')
                    return {'loginId': 'login-123',
                            'authUrl': 'https://chatgpt.com/codex/login?state=opaque'}
                if method == 'account/read':
                    return _account('pro')
                raise AssertionError(method)

            def close(self):
                pass

        self_outer = self
        fake = FakeClient()
        with patch.object(runtime, 'installed_mode', return_value=True), \
                patch.object(codex_setup, '_executable', return_value='mock-codex.exe'), \
                patch.object(codex_setup, '_version', return_value='2.0.0'), \
                patch.object(manager, '_get_client', return_value=fake):
            worker = threading.Thread(target=manager._login_worker, daemon=True)
            worker.start()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with manager._lock:
                    if manager._phase == 'login':
                        break
                time.sleep(0.01)
            with manager._lock:
                self.assertEqual(manager._phase, 'login')
                self.assertTrue(manager._login_url.startswith('https://chatgpt.com/'))
            manager._on_notification('account/login/completed', {'loginId': 'login-123', 'success': True})
            worker.join(timeout=2)
            result = manager.status()

        self.assertFalse(worker.is_alive())
        self.assertTrue(result['ready'])
        self.assertEqual(result['phase'], 'ready')
        self.assertNotIn('opaque', json.dumps(result))

    def test_login_url_is_restricted_to_official_https_hosts(self):
        self.assertTrue(codex_setup._safe_auth_url('https://chatgpt.com/codex/login?state=opaque'))
        self.assertTrue(codex_setup._safe_auth_url('https://auth.openai.com/codex/login'))
        self.assertTrue(codex_setup._safe_auth_url('https://chatgpt.com:443/codex/login'))
        self.assertIsNone(codex_setup._safe_auth_url('http://chatgpt.com/login'))
        self.assertIsNone(codex_setup._safe_auth_url('https://sub.auth.openai.com/login'))
        self.assertIsNone(codex_setup._safe_auth_url('https://chatgpt.com./login'))
        self.assertIsNone(codex_setup._safe_auth_url('https://chatgpt.com:8443/login'))
        self.assertIsNone(codex_setup._safe_auth_url('https://user@chatgpt.com/login'))
        self.assertIsNone(codex_setup._safe_auth_url('https://chatgpt.com.example.org/login'))

    def test_download_redirect_is_checked_before_following(self):
        handler = codex_setup._TrustedDownloadRedirectHandler()
        request = urllib.request.Request('https://github.com/openai/codex/releases/latest')
        response_headers = {}

        allowed = handler.redirect_request(
            request, None, 302, 'Found', response_headers,
            'https://release-assets.githubusercontent.com/codex.zip',
        )
        self.assertEqual(allowed.full_url, 'https://release-assets.githubusercontent.com/codex.zip')

        for destination in (
            'https://attacker.example/codex.zip',
            'http://objects.githubusercontent.com/codex.zip',
            'https://objects.githubusercontent.com:8443/codex.zip',
            '//attacker.example/codex.zip',
        ):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(codex_setup.CodexSetupError, 'untrusted location'):
                    handler.redirect_request(
                        request, None, 302, 'Found', response_headers, destination,
                    )

    def test_safe_extract_verifies_required_file_hash(self):
        raw = b'Codex test executable'
        with _tempdir() as temporary:
            root = Path(temporary)
            archive_path = root / 'codex.zip'
            with zipfile.ZipFile(archive_path, 'w') as archive:
                archive.writestr('codex.exe', raw)
            manifest = {'files': {'codex.exe': hashlib.sha256(raw).hexdigest()}}
            destination = root / 'staging'

            codex_setup._safe_extract_archive(archive_path, destination, manifest)

            self.assertEqual((destination / 'codex.exe').read_bytes(), raw)

    def test_safe_extract_renames_platform_executable_from_manifest(self):
        raw = b'Codex Windows executable'
        archive_name = 'codex-x86_64-pc-windows-msvc.exe'
        with _tempdir() as temporary:
            root = Path(temporary)
            archive_path = root / 'codex.zip'
            with zipfile.ZipFile(archive_path, 'w') as archive:
                archive.writestr(archive_name, raw)
            manifest = {
                'archive_executable': archive_name,
                'files_sha256': {'codex.exe': hashlib.sha256(raw).hexdigest()},
            }
            destination = root / 'staging'

            codex_setup._safe_extract_archive(archive_path, destination, manifest)

            self.assertEqual((destination / 'codex.exe').read_bytes(), raw)
            self.assertFalse((destination / archive_name).exists())

    def test_safe_extract_rejects_path_traversal(self):
        with _tempdir() as temporary:
            root = Path(temporary)
            archive_path = root / 'codex.zip'
            with zipfile.ZipFile(archive_path, 'w') as archive:
                archive.writestr('codex.exe', b'codex')
                archive.writestr('../outside.txt', b'unsafe')
            manifest = {'files': ['codex.exe']}

            with self.assertRaisesRegex(codex_setup.CodexSetupError, 'unsafe path'):
                codex_setup._safe_extract_archive(archive_path, root / 'staging', manifest)
            self.assertFalse((root / 'outside.txt').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
