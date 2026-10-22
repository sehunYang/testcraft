"""Hidden Windows desktop launcher for the installed Question Studio app."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hmac
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _arguments(argv=None):
    parser = argparse.ArgumentParser(description='Question Studio desktop launcher')
    parser.add_argument('--port', type=int, default=8765, help='loopback HTTP port (default: 8765; 0 selects a free port)')
    parser.add_argument('--no-browser', action='store_true', help='start the local app without opening a browser')
    parser.add_argument('--stop', action='store_true', help='stop this installed app instance after verifying its identity')
    parser.add_argument('--data-dir', help='isolated per-user data root used by smoke tests')
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    return args


class _InstanceLock:
    """Small OS file lock, held for the lifetime of this app process."""
    def __init__(self, path):
        self.path = Path(path)
        self.file = None
        self.locked = False

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('a+b')
        self.file.seek(0, os.SEEK_END)
        if self.file.tell() == 0:
            self.file.write(b'\0')
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            self.file.close()
            self.file = None
            return False
        self.locked = True
        return True

    def release(self):
        if self.file is None:
            return
        try:
            if self.locked:
                self.file.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file = None
            self.locked = False


def _read_record(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _write_record(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def _remove_file(path):
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass


def _remove_our_record(path, base_url, stop_token=None):
    record = _read_record(path)
    if (record and record.get('pid') == os.getpid() and record.get('base_url') == base_url
            and (stop_token is None or record.get('stop_token') == stop_token)):
        _remove_file(path)


def _pid_alive(pid):
    if type(pid) is not int or pid <= 0:
        return False
    if os.name == 'nt':
        # os.kill(pid, 0) is unreliable for Windows process discovery: access
        # denied can mean either a live process or an invalid/stale PID. Query
        # only limited process information, then check its exit status.
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED: conservatively treat as live
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (ProcessLookupError, OSError):
        return False
    return True


def _health(base_url, expected_identity, expected_version, expected_data_dir, timeout=0.7):
    try:
        request = urllib.request.Request(base_url + '/api/health', headers={'Host': '127.0.0.1'})
        # This endpoint is strictly loopback. Bypass configured system or
        # environment proxies so local instance discovery cannot be diverted.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                return False
            value = json.loads(response.read().decode('utf-8'))
        if not isinstance(value, dict):
            return False
        return (value.get('identity') == expected_identity
                and value.get('version') == expected_version
                and _path_key(value.get('data_dir', '')) == _path_key(expected_data_dir))
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _path_key(path):
    try:
        return os.path.normcase(os.path.abspath(os.fspath(path)))
    except (TypeError, ValueError):
        return ''


def _valid_record(record, identity, version, data_dir, install_root=None):
    if not isinstance(record, dict) or record.get('identity') != identity or record.get('version') != version:
        return False
    if _path_key(record.get('data_dir', '')) != _path_key(data_dir) or not _pid_alive(record.get('pid')):
        return False
    if install_root is not None and _path_key(record.get('install_root', '')) != _path_key(install_root):
        return False
    base_url = record.get('base_url')
    if not isinstance(base_url, str):
        return False
    try:
        parsed = urllib.parse.urlsplit(base_url)
        port = parsed.port
    except ValueError:
        return False
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or port is None
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        return False
    return _health(base_url, identity, version, data_dir), base_url


def _claim_instance(lock_path, record_path, identity, version, data_dir, wait_seconds=8, install_root=None):
    lock = _InstanceLock(lock_path)
    deadline = time.monotonic() + wait_seconds
    while True:
        if lock.acquire():
            return lock, None
        record = _read_record(record_path)
        check = _valid_record(record, identity, version, data_dir, install_root)
        if check:
            healthy, base_url = check
            if healthy:
                return None, base_url
        if time.monotonic() >= deadline:
            raise RuntimeError('이미 실행 중인 Question Studio 인스턴스를 확인할 수 없습니다. 로그를 확인하거나 기존 앱을 닫아 주세요.')
        time.sleep(0.2)


def _stop_request_matches(request, record):
    if not isinstance(request, dict) or not isinstance(record, dict):
        return False
    if (request.get('identity') != record.get('identity')
            or request.get('version') != record.get('version')
            or request.get('pid') != record.get('pid')
            or _path_key(request.get('data_dir', '')) != _path_key(record.get('data_dir', ''))
            or _path_key(request.get('install_root', '')) != _path_key(record.get('install_root', ''))):
        return False
    request_token = request.get('stop_token')
    record_token = record.get('stop_token')
    return (isinstance(request_token, str) and isinstance(record_token, str)
            and request_token.isascii() and record_token.isascii()
            and hmac.compare_digest(request_token, record_token))


def _stop_response_path(user_root, identity, request_id):
    if (not isinstance(request_id, str) or len(request_id) != 32
            or any(char not in '0123456789abcdef' for char in request_id)):
        return None
    return Path(user_root) / f'{identity}.stop-response-{request_id}.json'


def _remove_stop_request(path, request_id):
    request = _read_record(path)
    if request and request.get('request_id') == request_id:
        _remove_file(path)


def _has_running_jobs(jobs):
    try:
        return any(isinstance(job, dict) and job.get('status') == 'running'
                   for job in list(jobs.values()))
    except RuntimeError:
        # A changing job registry is unsafe to treat as idle.
        return True


def _handle_stop_request(request_path, user_root, record, jobs, server, core, stop_flag):
    request = _read_record(request_path)
    if not _stop_request_matches(request, record):
        return None
    request_id = request.get('request_id')
    response_path = _stop_response_path(user_root, record.get('identity'), request_id)
    if response_path is None:
        return None

    with core.LOCK:
        if _has_running_jobs(jobs):
            status = 'busy'
            message = 'AI 작업이 진행 중이어서 Question Studio를 종료하지 않았습니다. 작업이 끝난 뒤 다시 종료해 주세요.'
        else:
            # Serialize this transition with launch_job so a new worker cannot
            # start after the idle check but before the server shuts down.
            stop_flag.set()
            status = 'stopping'
            message = 'Question Studio is stopping.'
        try:
            _write_record(response_path, {
                'request_id': request_id, 'install_root': record.get('install_root'),
                'status': status, 'message': message,
            })
        except OSError:
            if status == 'stopping':
                stop_flag.clear()
            return None

    _remove_stop_request(request_path, request_id)
    if status == 'stopping':
        server.shutdown()
    return status


def _clean_stale_instance(user_root, record_path, request_path, record, install_root):
    if not isinstance(record, dict) or _path_key(record.get('install_root', '')) != _path_key(install_root):
        return
    pid = record.get('pid')
    if _pid_alive(pid):
        return
    current = _read_record(record_path)
    if (current and current.get('pid') == pid
            and current.get('stop_token') == record.get('stop_token')
            and _path_key(current.get('install_root', '')) == _path_key(install_root)):
        _remove_file(record_path)
    request = _read_record(request_path)
    if request and _stop_request_matches(request, record):
        _remove_file(request_path)
    for response_path in Path(user_root).glob('*.stop-response-*.json'):
        response = _read_record(response_path)
        if response and _path_key(response.get('install_root', '')) == _path_key(install_root):
            _remove_file(response_path)


def _create_server(server_type, handler_type, requested_port):
    try:
        return server_type(('127.0.0.1', requested_port), handler_type)
    except OSError:
        if requested_port != 8765:
            raise
        # Port 8765 belongs to another app or another install. A fresh bind(0)
        # gives this instance its own loopback port without contacting that app.
        return server_type(('127.0.0.1', 0), handler_type)


def _wait_for_health(base_url, runtime, data_dir, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _health(base_url, runtime.APP_ID, runtime.APP_VERSION, data_dir):
            return True
        time.sleep(0.15)
    return False


def _run(args, runtime):
    from app import core
    from app import server as server_module
    from app.server import Handler, StudioHTTPServer

    user_root = runtime.user_root(ROOT)
    data_dir = core.DATA.resolve()
    lock_path = user_root / (runtime.APP_ID + '.lock')
    record_path = user_root / (runtime.APP_ID + '.instance.json')
    stop_request_path = user_root / (runtime.APP_ID + '.stop-request.json')
    lock, existing_url = _claim_instance(lock_path, record_path, runtime.APP_ID,
                                          runtime.APP_VERSION, data_dir, install_root=ROOT)
    if existing_url:
        print(f'Reusing verified Question Studio instance at {existing_url}', flush=True)
        if not args.no_browser:
            webbrowser.open(existing_url + '/', new=2)
        return 0

    server = None
    server_thread = None
    base_url = None
    stop_token = secrets.token_urlsafe(32)
    stop_flag = threading.Event()
    original_launch_job = server_module.launch_job

    def guarded_launch_job(*job_args, **job_kwargs):
        with core.LOCK:
            if stop_flag.is_set():
                raise RuntimeError('Question Studio is shutting down.')
            return original_launch_job(*job_args, **job_kwargs)

    server_module.launch_job = guarded_launch_job
    try:
        stale_request = _read_record(stop_request_path)
        if (stale_request
                and _path_key(stale_request.get('install_root', '')) == _path_key(ROOT)):
            _remove_file(stop_request_path)
        for stale_response in user_root.glob(runtime.APP_ID + '.stop-response-*.json'):
            response = _read_record(stale_response)
            if response and _path_key(response.get('install_root', '')) == _path_key(ROOT):
                _remove_file(stale_response)
        core.DATA.mkdir(parents=True, exist_ok=True)
        server = _create_server(StudioHTTPServer, Handler, args.port)
        port = int(server.server_address[1])
        base_url = f'http://127.0.0.1:{port}'
        record = {
            'identity': runtime.APP_ID,
            'version': runtime.APP_VERSION,
            'pid': os.getpid(),
            'base_url': base_url,
            'data_dir': str(data_dir),
            'install_root': str(ROOT.resolve()),
            'stop_token': stop_token,
            'started_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        }
        _write_record(record_path, record)
        server_thread = threading.Thread(target=server.serve_forever,
                                         name='question-studio-http', daemon=True)
        server_thread.start()
        if not _wait_for_health(base_url, runtime, data_dir):
            raise RuntimeError('Question Studio 서버가 시작되지 않았습니다. 로그에서 오류를 확인해 주세요.')
        print(f'Question Studio {runtime.APP_VERSION} listening at {base_url} (data: {data_dir})', flush=True)
        if not args.no_browser:
            webbrowser.open(base_url + '/', new=2)
        stopping = False
        while server_thread.is_alive():
            server_thread.join(timeout=0.15)
            if not server_thread.is_alive():
                break
            result = _handle_stop_request(
                stop_request_path, user_root, record, server_module.JOBS,
                server, core, stop_flag,
            )
            if result == 'stopping':
                stopping = True
                break
        server_thread.join()
        if stopping:
            print(f'Question Studio stopped at {base_url}', flush=True)
        return 0
    finally:
        if server and server_thread and server_thread.is_alive():
            server.shutdown()
            server_thread.join(timeout=5)
        if server:
            server.server_close()
        if base_url:
            pending_request = _read_record(stop_request_path)
            if _stop_request_matches(pending_request, record):
                _remove_stop_request(stop_request_path, pending_request.get('request_id'))
            _remove_our_record(record_path, base_url, stop_token)
        if lock:
            lock.release()
        if not stop_flag.is_set():
            server_module.launch_job = original_launch_job


def _stop(args, runtime):
    from app import core

    user_root = runtime.user_root(ROOT)
    data_dir = core.DATA.resolve()
    lock_path = user_root / (runtime.APP_ID + '.lock')
    record_path = user_root / (runtime.APP_ID + '.instance.json')
    request_path = user_root / (runtime.APP_ID + '.stop-request.json')
    deadline = time.monotonic() + 8

    while True:
        probe = _InstanceLock(lock_path)
        if probe.acquire():
            try:
                record = _read_record(record_path)
                _clean_stale_instance(user_root, record_path, request_path, record, ROOT)
            finally:
                probe.release()
            print('Question Studio is not running.', flush=True)
            return 0

        record = _read_record(record_path)
        if record is not None:
            if _path_key(record.get('install_root', '')) != _path_key(ROOT):
                print('This installation has no running Question Studio instance.', flush=True)
                return 0
            if (record.get('identity') != runtime.APP_ID
                    or record.get('version') != runtime.APP_VERSION
                    or _path_key(record.get('data_dir', '')) != _path_key(data_dir)
                    ):
                raise RuntimeError('현재 설치의 실행 인스턴스를 안전하게 확인할 수 없습니다.')
            validation = _valid_record(
                record, runtime.APP_ID, runtime.APP_VERSION, data_dir, install_root=ROOT,
            )
            if validation and validation[0]:
                break

        if time.monotonic() >= deadline:
            raise RuntimeError('실행 중인 Question Studio 인스턴스의 상태를 확인할 수 없습니다.')
        time.sleep(0.15)

    stop_token = record.get('stop_token')
    if not isinstance(stop_token, str) or len(stop_token) < 32:
        raise RuntimeError('현재 설치의 종료 토큰을 확인할 수 없습니다.')
    request_id = secrets.token_hex(16)
    response_path = _stop_response_path(user_root, runtime.APP_ID, request_id)
    request = {
        'identity': runtime.APP_ID,
        'version': record['version'],
        'pid': record['pid'],
        'data_dir': str(data_dir),
        'install_root': str(ROOT.resolve()),
        'stop_token': stop_token,
        'request_id': request_id,
    }
    _write_record(request_path, request)
    try:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            response = _read_record(response_path)
            if response and response.get('request_id') == request_id:
                if _path_key(response.get('install_root', '')) != _path_key(ROOT):
                    raise RuntimeError('종료 응답이 다른 설치에서 왔습니다.')
                if response.get('status') == 'busy':
                    raise RuntimeError(response.get('message') or 'AI 작업이 진행 중이어서 앱을 종료하지 않았습니다.')
                if response.get('status') == 'stopping':
                    break
                raise RuntimeError('Question Studio가 종료 요청을 확인할 수 없습니다.')
            current = _read_record(record_path)
            if not _pid_alive(record.get('pid')):
                return 0
            if not current or current.get('stop_token') != stop_token:
                break
            time.sleep(0.15)
        else:
            raise RuntimeError('Question Studio가 종료 요청에 응답하지 않았습니다.')

        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if not _pid_alive(record.get('pid')):
                return 0
            time.sleep(0.15)
        raise RuntimeError('Question Studio가 제한 시간 안에 종료되지 않았습니다.')
    finally:
        _remove_stop_request(request_path, request_id)
        _remove_file(response_path)


def main(argv=None):
    args = _arguments(argv)
    os.environ['QUESTION_STUDIO_INSTALLED'] = '1'
    if args.data_dir:
        os.environ['QUESTION_STUDIO_DATA_DIR'] = str(Path(args.data_dir).expanduser().resolve())
    os.environ.setdefault('PYTHONUTF8', '1')
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app import runtime

    logs = runtime.log_dir(ROOT)
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / 'desktop.log'
    with log_path.open('a', encoding='utf-8', buffering=1) as log:
        with redirect_stdout(log), redirect_stderr(log):
            try:
                return _stop(args, runtime) if args.stop else _run(args, runtime)
            except BaseException:
                traceback.print_exc()
                return 1


if __name__ == '__main__':
    raise SystemExit(main())
