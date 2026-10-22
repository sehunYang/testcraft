"""Private Codex app-server lifecycle, ChatGPT entitlement and safe CLI repair."""
from datetime import datetime, timezone
import atexit
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile

from . import runtime


ROOT = Path(__file__).resolve().parents[1]
PAID_CHATGPT_PLANS = frozenset({'plus', 'pro', 'team', 'business', 'enterprise', 'edu'})
MAX_ARCHIVE_BYTES = 500 * 1024 * 1024
MAX_UNPACKED_BYTES = 1200 * 1024 * 1024
MAX_APP_SERVER_LINE = 2 * 1024 * 1024
_APP_SERVER_TIMEOUT = 25
_LOGIN_TIMEOUT = 15 * 60
_SAFE_LOGIN_HOSTS = frozenset({'chatgpt.com', 'auth.openai.com'})
_DOWNLOAD_HOSTS = frozenset({'github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com'})


class CodexSetupError(RuntimeError):
    """An error safe to return to the local UI; never contains process output."""


def _manifest_path():
    return ROOT / 'runtime' / 'codex' / 'manifest.json'


def _read_manifest():
    try:
        value = json.loads(_manifest_path().read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            return {}
        return value
    except (OSError, ValueError):
        return {}


def _version():
    value = _read_manifest().get('version')
    return value.strip()[:80] if isinstance(value, str) and value.strip() else None


def _manifest_files(manifest):
    """Accept both the original `files` name and builder `files_sha256` name."""
    return manifest.get('files_sha256', manifest.get('files'))


def _executable():
    # Keep executable discovery in one place so jobs and app-server use the
    # same user repair copy, bundled binary, or development CLI.
    from . import cli
    return cli.discover('codex')


def _safe_auth_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        return None
    try:
        parsed = urllib.parse.urlsplit(value)
        host = (parsed.hostname or '').lower()
        if (parsed.scheme != 'https' or parsed.username or parsed.password or not parsed.netloc
                or host not in _SAFE_LOGIN_HOSTS or parsed.port not in (None, 443)):
            return None
        return value
    except ValueError:
        return None


def derive_account_state(account_response, *, installed=True, version=None):
    """Map account/read to the subscription gate without retaining account data."""
    result = account_response if isinstance(account_response, dict) else {}
    account = result.get('account')
    if not isinstance(account, dict):
        account = None
    authenticated = bool(account and account.get('type') == 'chatgpt'
                         and result.get('requiresOpenaiAuth') is True)
    plan = None
    if authenticated:
        raw_plan = account.get('planType')
        if isinstance(raw_plan, str) and raw_plan.strip():
            plan = raw_plan.strip().lower()[:40]
    ready = bool(installed and authenticated and plan in PAID_CHATGPT_PLANS)
    if ready:
        phase, error = 'ready', None
    elif not installed:
        phase, error = 'missing', 'Codex is not installed. Install or repair it to continue.'
    elif authenticated and plan:
        phase, error = 'plan_required', 'A paid ChatGPT plan is required. The current account plan is not eligible.'
    elif authenticated:
        phase, error = 'plan_required', 'A paid ChatGPT plan is required, but the current plan could not be confirmed.'
    else:
        phase, error = 'login_required', 'Sign in with an eligible paid ChatGPT plan to continue.'
    return {
        'required': True,
        'installed': bool(installed),
        'version': version,
        'authenticated': authenticated,
        'plan': plan,
        'ready': ready,
        'phase': phase,
        'error': error,
    }


def _development_status():
    return {
        'required': False,
        'installed': bool(_executable()),
        'version': _version(),
        'authenticated': True,
        'plan': 'development',
        'ready': True,
        'phase': 'ready',
        'error': None,
    }


class _AppServerClient:
    """One hidden app-server stdio connection with a JSON-RPC reader thread."""
    def __init__(self, executable, notification):
        home = runtime.codex_home(ROOT)
        home.mkdir(parents=True, exist_ok=True)
        env = runtime.codex_environment(ROOT, executable=executable)
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        try:
            self.process = subprocess.Popen(
                [str(executable), 'app-server'], cwd=str(home), env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', errors='replace', bufsize=1,
                creationflags=flags,
            )
        except OSError as exc:
            # Do not include the exception text; process errors can expose local paths.
            raise CodexSetupError('Codex app-server could not start. Repair Codex and try again.') from exc
        self._notification = notification
        self._id_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending = {}
        self._next_id = 0
        self._closed = threading.Event()
        self._reader = threading.Thread(target=self._read_loop, name='question-studio-codex-rpc', daemon=True)
        self._reader.start()
        try:
            result = self.request('initialize', {'clientInfo': {
                'name': 'question_studio', 'title': 'Question Studio', 'version': runtime.APP_VERSION,
            }}, timeout=_APP_SERVER_TIMEOUT)
            if not isinstance(result, dict):
                raise CodexSetupError('Codex app-server did not initialize correctly.')
            self.notify('initialized', {})
        except Exception:
            self.close()
            raise

    def _read_loop(self):
        try:
            while self.process.poll() is None:
                line = self.process.stdout.readline()
                if not line:
                    break
                if len(line) > MAX_APP_SERVER_LINE:
                    break
                try:
                    message = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(message, dict):
                    continue
                if 'id' in message:
                    with self._pending_lock:
                        waiting = self._pending.get(message.get('id'))
                    if waiting is not None:
                        waiting.put(message)
                    elif isinstance(message.get('method'), str):
                        # No server-initiated auth requests are expected because
                        # this process is isolated from API-key and external-token modes.
                        self._send({'id': message.get('id'), 'error': {
                            'code': -32601, 'message': 'Unsupported server request',
                        }})
                elif isinstance(message.get('method'), str):
                    try:
                        self._notification(message.get('method'), message.get('params') or {})
                    except Exception:
                        pass
        finally:
            self._closed.set()
            with self._pending_lock:
                pending = list(self._pending.values())
            for waiting in pending:
                try:
                    waiting.put_nowait({'_closed': True})
                except queue.Full:
                    pass

    def _send(self, message):
        if self._closed.is_set() or self.process.poll() is not None:
            raise CodexSetupError('Codex app-server stopped. Restart the app and try again.')
        try:
            raw = json.dumps(message, ensure_ascii=False, separators=(',', ':'))
            with self._write_lock:
                self.process.stdin.write(raw + '\n')
                self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise CodexSetupError('Could not communicate with Codex app-server.') from exc

    def notify(self, method, params):
        self._send({'method': method, 'params': params})

    def request(self, method, params=None, timeout=_APP_SERVER_TIMEOUT):
        with self._id_lock:
            self._next_id += 1
            request_id = self._next_id
        waiting = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = waiting
        try:
            self._send({'method': method, 'id': request_id, 'params': params or {}})
            try:
                response = waiting.get(timeout=timeout)
            except queue.Empty as exc:
                raise CodexSetupError('Codex app-server did not respond in time.') from exc
            if response.get('_closed'):
                raise CodexSetupError('Codex app-server stopped. Restart the app and try again.')
            if 'error' in response:
                raise CodexSetupError('Codex app-server rejected the request. Repair Codex and try again.')
            return response.get('result')
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except OSError:
                    pass
        self._closed.set()


def _normalize_manifest_files(files, archive_executable=None):
    """Normalize deployed-path hashes to archive paths and safe destinations.

    Release manifests name installed files in ``files`` while
    ``archive_executable`` records the upstream executable's archive filename.
    The CLI is always installed as ``codex.exe`` even when upstream changes
    its platform-specific executable name.
    """
    normalized = {}
    if isinstance(files, dict):
        entries = []
        for deployed_path, value in files.items():
            if isinstance(value, str) and re.fullmatch(r'[a-fA-F0-9]{64}', value):
                source = archive_executable if (
                    isinstance(archive_executable, str)
                    and PurePosixPath(deployed_path.replace('\\', '/')).name.lower() == 'codex.exe'
                ) else deployed_path
                entries.append({'archive': source, 'destination': deployed_path, 'sha256': value})
            elif isinstance(value, str):
                entries.append({'archive': deployed_path, 'destination': value})
            elif isinstance(value, dict):
                entries.append({'destination': deployed_path, **value})
            else:
                return None
    elif isinstance(files, list):
        entries = files
    else:
        return None
    for item in entries:
        if isinstance(item, str):
            source = destination = item
            expected_hash = None
        elif isinstance(item, dict):
            source = item.get('archive') or item.get('archive_path') or item.get('path')
            destination = item.get('destination') or item.get('install_path') or item.get('path')
            expected_hash = item.get('sha256')
        else:
            return None
        if not isinstance(source, str) or not isinstance(destination, str):
            return None
        source = _safe_relative_path(source)
        destination = _safe_relative_path(destination)
        if source is None or destination is None:
            return None
        if expected_hash is not None and (not isinstance(expected_hash, str) or not re.fullmatch(r'[a-fA-F0-9]{64}', expected_hash)):
            return None
        if source in normalized:
            return None
        normalized[source] = (destination, expected_hash.lower() if expected_hash else None)
    if not normalized or not any(PurePosixPath(dest).name.lower() == 'codex.exe' for dest, _ in normalized.values()):
        return None
    return normalized


def _safe_relative_path(value):
    value = value.replace('\\', '/')
    path = PurePosixPath(value)
    if (not value or value.startswith('/') or ':' in value or '\x00' in value
            or any(part in ('', '.', '..') for part in path.parts)):
        return None
    return '/'.join(path.parts)


def _download_url(url):
    if not isinstance(url, str):
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
        return (parsed.scheme == 'https' and not parsed.username and not parsed.password
                and (parsed.hostname or '').lower() in _DOWNLOAD_HOSTS
                and parsed.port in (None, 443))
    except ValueError:
        return False


class _TrustedDownloadRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate a redirect target before urllib makes a request to it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urllib.parse.urljoin(req.full_url, newurl)
        if not _download_url(destination):
            raise CodexSetupError('Codex download redirected to an untrusted location.')
        return super().redirect_request(req, fp, code, msg, headers, destination)


def _safe_extract_archive(archive_path, destination, manifest):
    expected = _normalize_manifest_files(
        _manifest_files(manifest), manifest.get('archive_executable'),
    )
    if expected is None:
        raise CodexSetupError('Codex repair manifest is invalid.')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = {}
            total_size = 0
            for info in archive.infolist():
                if info.is_dir():
                    continue
                archive_name = _safe_relative_path(info.filename)
                if archive_name is None:
                    raise CodexSetupError('Codex repair archive contains an unsafe path.')
                mode = (info.external_attr >> 16) & 0xFFFF
                if mode and (mode & 0o170000) == 0o120000:
                    raise CodexSetupError('Codex repair archive contains an unsafe link.')
                total_size += info.file_size
                if info.file_size > MAX_ARCHIVE_BYTES or total_size > MAX_UNPACKED_BYTES:
                    raise CodexSetupError('Codex repair archive is too large.')
                members[archive_name] = info
            by_suffix = {}
            for name in members:
                for expected_name in expected:
                    if name == expected_name or name.endswith('/' + expected_name):
                        by_suffix.setdefault(expected_name, []).append(name)
            for source, (dest, expected_hash) in expected.items():
                name = source if source in members else None
                if name is None:
                    matches = by_suffix.get(source, [])
                    if len(matches) != 1:
                        raise CodexSetupError('Codex repair archive is missing a required file.')
                    name = matches[0]
                info = members[name]
                relative = Path(*PurePosixPath(dest).parts)
                target = (destination / relative).resolve()
                if destination.resolve() not in target.parents:
                    raise CodexSetupError('Codex repair archive contains an unsafe path.')
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.open(info) as source_stream, target.open('wb') as target_stream:
                    while True:
                        chunk = source_stream.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        target_stream.write(chunk)
                if expected_hash and digest.hexdigest().lower() != expected_hash:
                    raise CodexSetupError('Codex repair archive file verification failed.')
    except CodexSetupError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as exc:
        raise CodexSetupError('Codex repair archive could not be extracted safely.') from exc
    if not any(path.is_file() for path in destination.rglob('codex.exe')):
        raise CodexSetupError('Codex repair archive does not contain codex.exe.')


def _download_and_install():
    manifest = _read_manifest()
    url = manifest.get('url')
    archive_hash = manifest.get('archive_sha256')
    if not _download_url(url) or not isinstance(archive_hash, str) or not re.fullmatch(r'[a-fA-F0-9]{64}', archive_hash):
        raise CodexSetupError('Codex repair manifest is missing or invalid.')
    if _normalize_manifest_files(_manifest_files(manifest), manifest.get('archive_executable')) is None:
        raise CodexSetupError('Codex repair manifest is missing its file list.')
    user_root = runtime.user_root(ROOT)
    tools_root = user_root / 'tools'
    target = tools_root / 'codex'
    tools_root.mkdir(parents=True, exist_ok=True)
    staging = tools_root / ('.codex-stage-' + uuid.uuid4().hex)
    backup = tools_root / ('.codex-backup-' + uuid.uuid4().hex)
    archive_path = None
    try:
        fd, archive_name = tempfile.mkstemp(prefix='question-studio-codex-', suffix='.zip', dir=str(user_root))
        archive_path = Path(archive_name)
        digest = hashlib.sha256()
        total = 0
        try:
            opener = urllib.request.build_opener(_TrustedDownloadRedirectHandler())
            with os.fdopen(fd, 'wb') as output, opener.open(url, timeout=45) as response:
                final_url = response.geturl()
                if not _download_url(final_url):
                    raise CodexSetupError('Codex download redirected to an untrusted location.')
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise CodexSetupError('Codex download is too large.')
                    digest.update(chunk)
                    output.write(chunk)
        except CodexSetupError:
            raise
        except Exception as exc:
            raise CodexSetupError('Codex could not be downloaded. Check the connection and try again.') from exc
        if digest.hexdigest().lower() != archive_hash.lower():
            raise CodexSetupError('Codex download verification failed.')
        _safe_extract_archive(archive_path, staging, manifest)
        if target.exists():
            os.replace(target, backup)
        try:
            os.replace(staging, target)
        except Exception:
            if backup.exists() and not target.exists():
                os.replace(backup, target)
            raise
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
    except CodexSetupError:
        raise
    except OSError as exc:
        raise CodexSetupError('Codex could not be installed in the per-user tools folder.') from exc
    finally:
        if archive_path:
            try:
                archive_path.unlink()
            except FileNotFoundError:
                pass
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if backup.exists() and target.exists():
            shutil.rmtree(backup, ignore_errors=True)


class CodexSetup:
    def __init__(self):
        self._lock = threading.RLock()
        self._client_lock = threading.Lock()
        self._client = None
        self._phase = 'idle'
        self._error = None
        self._authenticated = False
        self._plan = None
        self._ready = False
        self._login_id = None
        self._login_url = None
        self._login_event = None
        self._login_completion = None
        self._early_completions = {}
        self._last_check = 0.0

    def close(self):
        with self._client_lock:
            client = self._client
            self._client = None
        if client:
            client.close()

    def _set_account(self, response):
        status = derive_account_state(response, installed=bool(_executable()), version=_version())
        with self._lock:
            self._authenticated = status['authenticated']
            self._plan = status['plan']
            self._ready = status['ready']
            self._phase = status['phase']
            self._error = status['error']
            self._last_check = time.monotonic()
            self._login_id = None
            self._login_url = None
            self._login_event = None
        return status

    def _set_safe_error(self, message):
        with self._lock:
            self._phase = 'error'
            self._error = message
            self._ready = False
            self._last_check = time.monotonic()
            self._login_url = None

    def _on_notification(self, method, params):
        if method != 'account/login/completed' or not isinstance(params, dict):
            return
        login_id = params.get('loginId')
        if not isinstance(login_id, str):
            return
        with self._lock:
            success = params.get('success') is True
            if self._phase == 'cancelling':
                success = False
            self._early_completions[login_id] = success
            if self._login_id == login_id and self._login_event:
                self._login_completion = success
                self._login_event.set()

    def _get_client(self):
        with self._client_lock:
            if (self._client and self._client.process.poll() is None
                    and not self._client._closed.is_set()):
                return self._client
            if self._client:
                self._client.close()
                self._client = None
            executable = _executable()
            if not executable:
                raise CodexSetupError('Codex is not installed. Install or repair it to continue.')
            client = _AppServerClient(executable, self._on_notification)
            self._client = client
            return client

    def _check_worker(self):
        try:
            client = self._get_client()
            response = client.request('account/read', {'refreshToken': False})
            if not isinstance(response, dict):
                raise CodexSetupError('Codex app-server returned an invalid account response.')
            self._set_account(response)
        except CodexSetupError as exc:
            self._set_safe_error(str(exc))
        except Exception:
            self._set_safe_error('Could not check ChatGPT sign-in status. Restart the app or repair Codex.')

    def _start_check(self):
        with self._lock:
            if self._phase in ('checking', 'installing', 'login_starting', 'login', 'cancelling'):
                return
            if self._last_check and time.monotonic() - self._last_check < 30:
                return
            self._phase = 'checking'
            self._error = None
        threading.Thread(target=self._check_worker, name='question-studio-codex-check', daemon=True).start()

    def status(self):
        required = runtime.installed_mode()
        if not required:
            return _development_status()
        installed = bool(_executable())
        version = _version()
        if installed:
            self._start_check()
        else:
            with self._lock:
                if self._phase not in ('installing', 'error'):
                    self._phase = 'missing'
                    self._error = 'Codex is not installed. Install or repair it to continue.'
                    self._ready = False
        with self._lock:
            state = {
                'required': True,
                'installed': installed,
                'version': version,
                'authenticated': bool(self._authenticated),
                'plan': self._plan,
                'ready': bool(installed and self._ready),
                'phase': self._phase,
                'error': self._error,
            }
            if self._login_url:
                state['login_url'] = self._login_url
            return state

    def install(self, repair=False):
        if not runtime.installed_mode():
            return self.status()
        with self._lock:
            if self._phase == 'installing':
                return self.status()
            self._phase = 'installing'
            self._error = None
        threading.Thread(target=self._install_worker, args=(bool(repair),),
                         name='question-studio-codex-install', daemon=True).start()
        return self.status()

    def _install_worker(self, repair):
        try:
            user_copy = runtime.user_root(ROOT) / 'tools' / 'codex' / 'codex.exe'
            bundled = ROOT / 'runtime' / 'codex' / 'codex.exe'
            if user_copy.is_file() and not repair:
                pass
            elif bundled.is_file() and not repair:
                # The packaged CLI is already usable and remains the safe fallback.
                pass
            else:
                client = self._client
                if client:
                    client.close()
                    self._client = None
                _download_and_install()
            with self._lock:
                self._last_check = 0.0
                self._phase = 'checking' if _executable() else 'missing'
                self._error = None if _executable() else 'Codex installation did not produce codex.exe.'
            if _executable():
                self._check_worker()
        except CodexSetupError as exc:
            self._set_safe_error(str(exc))
        except Exception:
            self._set_safe_error('Codex could not be installed or repaired. Try again.')

    def login_start(self):
        if not runtime.installed_mode():
            return self.status()
        if not _executable():
            return self.status()
        with self._lock:
            if self._phase in ('login_starting', 'login', 'cancelling'):
                return self.status()
            self._phase = 'login_starting'
            self._error = None
            self._login_url = None
            self._login_id = None
            self._login_event = None
            self._login_completion = None
        threading.Thread(target=self._login_worker, name='question-studio-codex-login', daemon=True).start()
        return self.status()

    def _login_worker(self):
        try:
            client = self._get_client()
            result = client.request('account/login/start', {
                'type': 'chatgpt', 'useHostedLoginSuccessPage': True, 'appBrand': 'chatgpt',
            })
            if not isinstance(result, dict):
                raise CodexSetupError('ChatGPT sign-in could not be started.')
            login_id = result.get('loginId')
            login_url = _safe_auth_url(result.get('authUrl'))
            if not isinstance(login_id, str) or not login_id or not login_url:
                raise CodexSetupError('Codex returned an invalid ChatGPT sign-in link.')
            event = threading.Event()
            with self._lock:
                if self._phase == 'cancelling':
                    should_cancel = True
                else:
                    should_cancel = False
                self._login_id = login_id
                self._login_url = login_url
                self._login_event = event
                self._login_completion = self._early_completions.pop(login_id, None)
                if self._login_completion is not None:
                    event.set()
                if not should_cancel:
                    self._phase = 'login'
            if should_cancel:
                try:
                    client.request('account/login/cancel', {'loginId': login_id})
                finally:
                    with self._lock:
                        self._phase = 'login_required'
                        self._login_id = None
                        self._login_url = None
                        self._login_event = None
                        self._error = 'ChatGPT sign-in was canceled.'
                return
            if not event.wait(_LOGIN_TIMEOUT):
                with self._lock:
                    self._phase = 'login_required'
                    self._login_id = None
                    self._login_url = None
                    self._login_event = None
                    self._error = 'ChatGPT sign-in timed out. Start sign-in again to continue.'
                return
            with self._lock:
                success = self._login_completion is True
                self._login_url = None
            if not success:
                with self._lock:
                    self._phase = 'login_required'
                    self._login_id = None
                    self._login_event = None
                    self._error = 'ChatGPT sign-in was canceled or did not complete.'
                return
            response = client.request('account/read', {'refreshToken': False})
            if not isinstance(response, dict):
                raise CodexSetupError('ChatGPT sign-in completed, but account status could not be checked.')
            self._set_account(response)
        except CodexSetupError as exc:
            self._set_safe_error(str(exc))
        except Exception:
            self._set_safe_error('ChatGPT sign-in could not be completed. Start sign-in again.')

    def login_cancel(self):
        with self._lock:
            login_id = self._login_id
            event = self._login_event
            active = self._phase in ('login_starting', 'login', 'cancelling')
            if not active:
                return self.status()
            self._phase = 'cancelling'
            self._login_completion = False
            if event:
                event.set()
        if login_id:
            threading.Thread(target=self._cancel_worker, args=(login_id,),
                             name='question-studio-codex-cancel', daemon=True).start()
        return self.status()

    def _cancel_worker(self, login_id):
        try:
            client = self._get_client()
            client.request('account/login/cancel', {'loginId': login_id})
        except Exception:
            pass


setup = CodexSetup()
atexit.register(setup.close)


def status():
    return setup.status()


def install(repair=False):
    return setup.install(repair=repair)


def login_start():
    return setup.login_start()


def login_cancel():
    return setup.login_cancel()
