import hashlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from app import runtime, updates

BODY = b'x' * (updates.MIN_SIZE + 5)
SHA = hashlib.sha256(BODY).hexdigest()


def release(version='v9.9.9', **change):
    name = f'TestCraft-{version[1:]}-windows-x64-setup.exe'
    asset = {'kind': 'setup', 'name': name, 'url': f'{updates.DOWNLOAD_PREFIX}{version}/{name}',
             'size': len(BODY), 'digest': 'sha256:' + SHA}
    asset.update(change)
    return json.dumps({'version': version, 'assets': [asset]}).encode()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(updates._state)
        updates._state.update(checked_at=0.0, release=None, error='', stage='', received=0, install_error='')

    def tearDown(self):
        updates._state.clear(); updates._state.update(self.saved)

    def wait(self, done):
        for _ in range(200):
            if done():
                return
            time.sleep(.02)
        self.fail('업데이트 작업이 끝나지 않았습니다')

    def test_release_must_point_at_the_official_installer(self):
        self.assertEqual(updates.parse_release(release())['sha256'], SHA)
        for bad in (release(url='https://example.com/TestCraft-9.9.9-windows-x64-setup.exe'),
                    release(name='evil.exe'), release(digest='sha256:zz'), release(size=10),
                    release('v9.9'), release(kind='portable')):
            with self.assertRaises(ValueError):
                updates.parse_release(bad)

    def test_newer_version_is_announced_and_older_is_not(self):
        self.assertTrue(updates.check(get=lambda url: release())['available'])
        updates._state['checked_at'] = 0
        status = updates.check(get=lambda url: release('v0.0.1'))
        self.assertFalse(status['available'])
        self.assertEqual(status['current'], 'v' + runtime.APP_VERSION)
        self.assertGreater(updates.version_key('v1.10.0'), updates.version_key('v1.9.9'))

    def test_check_runs_once_a_day_and_survives_network_errors(self):
        calls = []
        def get(url):
            calls.append(url); return release()
        clock = [1000.0]
        updates.check(get=get, now=lambda: clock[0]); updates.check(get=get, now=lambda: clock[0] + 60)
        self.assertEqual(len(calls), 1)
        clock[0] += updates.CHECK_EVERY + 1
        def broken(url):
            raise OSError('offline')
        status = updates.check(get=broken, now=lambda: clock[0])
        self.assertIn('확인하지 못했습니다', status['error'])
        self.assertTrue(status['available'])          # 전에 확인한 새 버전 안내는 남는다

    def test_official_address_is_fixed_for_installed_apps(self):
        with mock.patch.dict('os.environ', {'QUESTION_STUDIO_RELEASE_URL': 'file:///x.json', 'QUESTION_STUDIO_INSTALLED': '1'}):
            self.assertEqual(updates.release_url(), updates.RELEASE_URL)
        with mock.patch.dict('os.environ', {'QUESTION_STUDIO_RELEASE_URL': 'file:///x.json', 'QUESTION_STUDIO_INSTALLED': ''}):
            self.assertEqual(updates.release_url(), 'file:///x.json')

    def test_download_verifies_size_and_hash_before_keeping_the_file(self):
        info = updates.parse_release(release())
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'TestCraft-0.0.1-windows-x64-setup.exe').write_bytes(b'old')
            path = updates.download(info, folder, lambda url: io.BytesIO(BODY))
            self.assertEqual(path.read_bytes(), BODY)
            self.assertEqual([p.name for p in folder.iterdir()], [info['name']])      # 지난 파일은 치운다
            # 이미 받은 올바른 파일은 다시 받지 않는다
            self.assertEqual(updates.download(info, folder, lambda url: self.fail('다시 받았습니다')), path)
        with tempfile.TemporaryDirectory() as tmp:
            for body in (BODY[:-1] + b'y', BODY[:-3], BODY + b'more'):
                with self.assertRaises(ValueError):
                    updates.download(info, Path(tmp), lambda url, body=body: io.BytesIO(body))
                self.assertEqual(list(Path(tmp).iterdir()), [])                         # 틀린 파일은 남기지 않는다

    def test_install_runs_the_verified_installer_only_on_installed_copies(self):
        updates.check(get=lambda url: release())
        with self.assertRaisesRegex(ValueError, '홈페이지'):
            updates.start_install()                    # 개발 모드·무설치 ZIP
        ran = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(updates, 'can_install', return_value=True), \
                mock.patch.object(updates, 'updates_dir', return_value=Path(tmp)):
            self.assertEqual(updates.start_install(ran.append, lambda url: io.BytesIO(BODY))['stage'], 'downloading')
            self.wait(lambda: updates.status()['stage'] == 'installing')
            self.assertEqual(ran[0].read_bytes(), BODY)
            self.assertEqual(updates.status()['received'], len(BODY))

    def test_bad_download_never_runs_the_installer(self):
        updates.check(get=lambda url: release())
        ran = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(updates, 'can_install', return_value=True), \
                mock.patch.object(updates, 'updates_dir', return_value=Path(tmp)):
            updates.start_install(ran.append, lambda url: io.BytesIO(b'tampered' * 10))
            self.wait(lambda: updates.status()['install_error'])
            self.assertEqual(ran, [])
            self.assertEqual(updates.status()['stage'], '')
            self.assertIn('SHA-256', updates.status()['install_error'])

    def test_no_install_when_already_latest(self):
        updates.check(get=lambda url: release('v0.0.1'))
        with mock.patch.object(updates, 'can_install', return_value=True):
            with self.assertRaisesRegex(ValueError, '새 버전이 없습니다'):
                updates.start_install(lambda path: self.fail('실행했습니다'))

    def test_installer_is_started_silently_with_relaunch(self):
        with mock.patch.object(updates.subprocess, 'Popen') as popen:
            updates.launch_installer(Path('C:/u/TestCraft-9.9.9-windows-x64-setup.exe'))
        args = popen.call_args[0][0]
        self.assertEqual(args[1:], ['/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/RELAUNCH'])
        script = (Path(__file__).resolve().parents[1] / 'packaging/TestCraft.iss').read_text(encoding='utf-8-sig')
        self.assertIn("'/RELAUNCH'", script)
        self.assertIn('Check: RelaunchRequested', script)


if __name__ == '__main__':
    unittest.main()
