# -*- coding: utf-8 -*-
"""새 버전 확인과 한 번 클릭 업데이트.

앱이 시작할 때와 하루 한 번 홈페이지의 release.json 을 읽어 새 버전이 있는지 본다(보내는 정보는 없다).
교사가 '지금 업데이트'를 누르면 설치 파일을 받아 크기와 SHA-256 을 확인한 뒤 설치 프로그램을 실행한다.
설치 프로그램이 앱을 닫고, 설치하고, 다시 연다. 무설치 ZIP 과 개발 모드에서는 알림과 다운로드 링크만 보인다.
"""
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from . import runtime

ROOT = Path(__file__).resolve().parents[1]
RELEASE_URL = 'https://shy.ai.kr/testcraft/release.json'
HOME_URL = 'https://shy.ai.kr/testcraft/#download'
NOTES_URL = 'https://github.com/sehunYang/testcraft/releases/tag/'
DOWNLOAD_PREFIX = 'https://github.com/sehunYang/testcraft/releases/download/'
CHECK_EVERY = 24 * 3600
MIN_SIZE, MAX_SIZE = 20 * 1024 * 1024, 2 * 1024 * 1024 * 1024
VERSION = re.compile(r'v(\d+)\.(\d+)\.(\d+)')

_lock = threading.Lock()
_state = {'checked_at': 0.0, 'release': None, 'error': '',
          'stage': '', 'received': 0, 'install_error': ''}


def release_url():
    """개발·시험 때만 다른 주소를 쓸 수 있다. 설치본은 항상 공식 주소를 읽는다."""
    override = os.environ.get('QUESTION_STUDIO_RELEASE_URL', '').strip()
    return override if override and not runtime.is_installed() else RELEASE_URL


def fetch(url, timeout=8):
    req = urllib.request.Request(url, headers={'User-Agent': f'TestCraft/{runtime.APP_VERSION}'})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read(4 * 1024 * 1024)


def version_key(text):
    match = VERSION.fullmatch(text if str(text).startswith('v') else f'v{text}')
    return tuple(int(part) for part in match.groups()) if match else None


def parse_release(raw):
    """release.json 에서 설치 파일 정보를 꺼낸다. 이름·주소·크기·해시가 정해진 꼴이 아니면 믿지 않는다."""
    data = json.loads(raw)
    version = str(data.get('version', ''))
    if not version_key(version):
        raise ValueError('버전 표기가 올바르지 않습니다.')
    name = f'TestCraft-{version[1:]}-windows-x64-setup.exe'
    asset = next((a for a in data.get('assets', []) if isinstance(a, dict) and a.get('kind') == 'setup'), None)
    if not asset or asset.get('name') != name or asset.get('url') != f'{DOWNLOAD_PREFIX}{version}/{name}':
        raise ValueError('설치 파일 정보가 올바르지 않습니다.')
    size, digest = asset.get('size'), str(asset.get('digest', ''))
    if not isinstance(size, int) or not MIN_SIZE <= size <= MAX_SIZE or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('설치 파일 크기 또는 해시가 올바르지 않습니다.')
    return {'version': version, 'name': name, 'url': asset['url'], 'size': size, 'sha256': digest[7:]}


def can_install():
    """설치 프로그램으로 깐 Windows 설치본에서만 앱이 직접 설치한다(제거 프로그램이 있는 폴더)."""
    return os.name == 'nt' and runtime.is_installed() and (ROOT / 'unins000.exe').is_file()


def updates_dir():
    return runtime.user_root(ROOT) / 'updates'


def check(force=False, get=fetch, now=time.time):
    """하루에 한 번(앱을 새로 켜면 그때 한 번) 새 버전을 확인한다. 실패해도 앱은 그대로 쓴다."""
    with _lock:
        due = force or not _state['checked_at'] or now() - _state['checked_at'] >= CHECK_EVERY
    if due:
        try:
            release, error = parse_release(get(release_url())), ''
        except Exception as e:
            release, error = None, f'새 버전을 확인하지 못했습니다: {e}'
        with _lock:
            _state.update(checked_at=now(), error=error)
            if release or not _state['release']:
                _state['release'] = release
    return status()


def status():
    with _lock:
        release = _state['release']
        current = version_key(runtime.APP_VERSION)
        newer = bool(release and current and version_key(release['version']) > current)
        return {'current': 'v' + runtime.APP_VERSION, 'latest': release['version'] if release else '',
                'available': newer, 'can_install': newer and can_install(),
                'size': release['size'] if newer else 0, 'home': HOME_URL,
                'notes': NOTES_URL + release['version'] if newer else '',
                'error': _state['error'], 'stage': _state['stage'], 'received': _state['received'],
                'install_error': _state['install_error']}


def _set(**values):
    with _lock:
        _state.update(values)


def download(release, folder, opener=None):
    """설치 파일을 받아 크기와 SHA-256 을 확인한다. 하나라도 다르면 지우고 멈춘다."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob('TestCraft-*-setup.exe*'):          # 지난 설치 파일과 받다 만 파일을 치운다
        if old.name != release['name']:
            old.unlink(missing_ok=True)
    target = folder / release['name']
    if target.is_file() and target.stat().st_size == release['size'] and _sha256(target) == release['sha256']:
        return target
    part = folder / (release['name'] + '.part')
    digest, received = hashlib.sha256(), 0
    opener = opener or (lambda url: urllib.request.urlopen(
        urllib.request.Request(url, headers={'User-Agent': f'TestCraft/{runtime.APP_VERSION}'}), timeout=60))
    try:
        with opener(release['url']) as res, open(part, 'wb') as out:
            while True:
                chunk = res.read(1024 * 256)
                if not chunk:
                    break
                received += len(chunk)
                if received > release['size']:
                    raise ValueError('받은 파일이 안내된 크기보다 큽니다.')
                digest.update(chunk); out.write(chunk)
                _set(received=received)
        if received != release['size'] or digest.hexdigest() != release['sha256']:
            raise ValueError('받은 설치 파일이 릴리스의 크기·SHA-256 과 다릅니다. 설치하지 않았습니다.')
        part.replace(target)
        return target
    finally:
        part.unlink(missing_ok=True)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def launch_installer(path):
    """설치 프로그램을 따로 띄운다. 진행 창만 보이고(/SILENT), 끝나면 앱을 다시 연다(/RELAUNCH).
    설치 프로그램이 실행 중인 앱을 먼저 닫으므로 이 프로세스는 곧 끝난다."""
    flags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
    subprocess.Popen([str(path), '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/RELAUNCH'],
                     cwd=str(path.parent), creationflags=flags, close_fds=True)


def start_install(run=launch_installer, opener=None):
    """받기 → 검증 → 설치 프로그램 실행을 백그라운드에서 한다. 이미 하는 중이면 상태만 돌려준다."""
    with _lock:
        release = _state['release']
        busy = _state['stage'] in ('downloading', 'installing')
        current = version_key(runtime.APP_VERSION)
        if not busy:
            if not (release and current and version_key(release['version']) > current):
                raise ValueError('설치할 새 버전이 없습니다.')
            if not can_install():
                raise ValueError('이 실행 방식에서는 홈페이지에서 새 버전을 받아 주세요.')
            _state.update(stage='downloading', received=0, install_error='')
    if busy:
        return status()

    def work():
        try:
            path = download(release, updates_dir(), opener)
            _set(stage='installing')
            run(path)
        except Exception as e:
            _set(stage='', install_error=f'업데이트하지 못했습니다: {e}')
    threading.Thread(target=work, name='testcraft-update', daemon=True).start()
    return status()
