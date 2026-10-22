from pathlib import Path
import os
import http.server
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from app import cli, desktop, runtime


def _tempdir():
    return tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.runtime')


class RuntimeTests(unittest.TestCase):
    def test_source_defaults_stay_in_checkout(self):
        with _tempdir() as temporary:
            root = Path(temporary) / 'checkout'
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(runtime.data_dir(root), root.resolve() / 'exams' / '_studio')
                self.assertEqual(runtime.label_cache_dir(root), root.resolve() / '.runtime' / 'labels-v2')

    def test_installed_paths_use_local_app_data(self):
        with _tempdir() as temporary:
            local = Path(temporary) / 'Local App Data'
            root = Path(temporary) / 'install'
            with patch.dict(os.environ, {
                'QUESTION_STUDIO_INSTALLED': '1', 'LOCALAPPDATA': str(local),
            }, clear=True):
                user_root = local / 'QuestionStudio'
                self.assertTrue(runtime.installed_mode())
                self.assertEqual(runtime.user_root(root), user_root.resolve())
                self.assertEqual(runtime.data_dir(root), user_root.resolve() / 'exams' / '_studio')
                self.assertEqual(runtime.label_cache_dir(root), user_root.resolve() / 'cache' / 'labels-v2')
                self.assertEqual(runtime.log_dir(root), user_root.resolve() / 'logs')

    def test_data_dir_override_is_an_isolated_user_root(self):
        with _tempdir() as temporary:
            override = Path(temporary) / 'smoke'
            root = Path(temporary) / 'install'
            with patch.dict(os.environ, {
                'QUESTION_STUDIO_INSTALLED': '1', 'QUESTION_STUDIO_DATA_DIR': str(override),
            }, clear=True):
                self.assertEqual(runtime.user_root(root), override.resolve())
                self.assertEqual(runtime.data_dir(root), override.resolve() / 'exams' / '_studio')
                self.assertEqual(runtime.label_cache_dir(root), override.resolve() / 'cache' / 'labels-v2')

    def test_bundled_node_and_modules_are_preferred(self):
        with _tempdir() as temporary:
            root = Path(temporary) / 'install'
            node = root / 'runtime' / 'node' / 'node.exe'
            node.parent.mkdir(parents=True)
            node.write_bytes(b'node')
            (root / 'node_modules').mkdir(parents=True)
            env = {'PATH': 'old-path', 'NODE_PATH': 'old-modules'}

            self.assertEqual(runtime.node_executable(root), str(node.resolve()))
            prepared = runtime.node_environment(root, env)
            self.assertEqual(
                prepared['NODE_PATH'],
                str((root / 'node_modules').resolve()) + os.pathsep + 'old-modules',
            )
            self.assertEqual(prepared['PATH'].split(os.pathsep)[0], str(node.parent.resolve()))

    def test_node_path_falls_back_to_development_path(self):
        with _tempdir() as temporary:
            root = Path(temporary) / 'checkout'
            with patch.object(runtime.shutil, 'which', side_effect=lambda name: 'node-from-path' if name == 'node.exe' else None):
                self.assertEqual(runtime.node_executable(root), 'node-from-path')
                self.assertEqual(runtime.node_environment(root, {'PATH': 'old-path'}), {'PATH': 'old-path'})

    def test_codex_environment_is_isolated_and_strips_api_keys(self):
        with _tempdir() as temporary:
            env = runtime.codex_environment(Path(temporary), {
                'CODEX_HOME': 'elsewhere', 'OPENAI_API_KEY': 'secret',
                'CODEX_API_KEY': 'also-secret', 'CODEX_ACCESS_TOKEN': 'access-token',
                'AZURE_OPENAI_API_KEY': 'azure-secret',
                'OPENAI_IDENTITY_TOKEN_FILE': 'identity-token-file',
                'OPENAI_FEDERATION_RULE_ID': 'federation-rule',
                'OPENAI_WORKLOAD_IDENTITY_CONTEXT': 'identity-context',
                'CODEX_EXEC_SERVER_NOISE_AUTH_TOKEN': 'noise-token',
                'CODEX_GUARDIAN_DECISIONS_API_KEY': 'guardian-key',
                'NODE_REPL_AUTH_TOKEN': 'node-repl-token',
                'PATH': 'system-path',
            })

            self.assertEqual(env['CODEX_HOME'], str((Path(temporary) / '.runtime' / 'codex-home').resolve()))
            self.assertEqual(env['PATH'], 'system-path')
            self.assertNotIn('OPENAI_API_KEY', env)
            self.assertNotIn('CODEX_API_KEY', env)
            self.assertNotIn('CODEX_ACCESS_TOKEN', env)
            self.assertNotIn('AZURE_OPENAI_API_KEY', env)
            self.assertNotIn('OPENAI_IDENTITY_TOKEN_FILE', env)
            self.assertNotIn('OPENAI_FEDERATION_RULE_ID', env)
            self.assertNotIn('OPENAI_WORKLOAD_IDENTITY_CONTEXT', env)
            self.assertNotIn('CODEX_EXEC_SERVER_NOISE_AUTH_TOKEN', env)
            self.assertNotIn('CODEX_GUARDIAN_DECISIONS_API_KEY', env)
            self.assertNotIn('NODE_REPL_AUTH_TOKEN', env)

    def test_installed_codex_discovery_prefers_repair_copy_then_bundle(self):
        with _tempdir() as temporary:
            temporary = Path(temporary)
            root = temporary / 'install'
            user_root = temporary / 'user'
            per_user = user_root / 'tools' / 'codex' / 'codex.exe'
            bundled = root / 'runtime' / 'codex' / 'codex.exe'
            launcher = temporary / 'launcher-codex.exe'
            legacy = temporary / 'legacy-codex.exe'
            for path in (per_user, bundled, launcher, legacy):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'codex')

            with patch.dict(os.environ, {
                'QUESTION_STUDIO_INSTALLED': '1',
                'QUESTION_STUDIO_CODEX_PATH': str(launcher),
                'QUESTION_MAKER_CODEX_PATH': str(legacy),
            }, clear=True), \
                    patch.object(cli, 'ROOT', root), \
                    patch.object(runtime, 'user_root', return_value=user_root), \
                    patch.object(runtime, 'installed_mode', return_value=True), \
                    patch.object(cli.shutil, 'which', return_value=None):
                self.assertEqual(cli.discover('codex'), str(per_user))
                per_user.unlink()
                self.assertEqual(cli.discover('codex'), str(bundled))
                bundled.unlink()
                self.assertEqual(cli.discover('codex'), str(launcher))
                launcher.unlink()
                self.assertEqual(cli.discover('codex'), str(legacy))

    def test_native_launcher_start_reuse_and_stop(self):
        with _tempdir() as temporary:
            user_root = Path(temporary) / 'user-data'
            repository = Path(__file__).resolve().parents[1]
            script = repository / 'app' / 'desktop.py'
            record_path = user_root / f'{runtime.APP_ID}.instance.json'
            log_path = user_root / 'logs' / 'desktop.log'
            environment = os.environ.copy()
            import_paths = [str(repository / '.runtime' / 'packages'), str(repository)]
            if environment.get('PYTHONPATH'):
                import_paths.append(environment['PYTHONPATH'])
            environment['PYTHONPATH'] = os.pathsep.join(import_paths)
            # Prove launcher health and reuse checks bypass configured proxies.
            environment.update({
                'HTTP_PROXY': 'http://127.0.0.1:9',
                'HTTPS_PROXY': 'http://127.0.0.1:9',
                'NO_PROXY': '',
            })
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            common_args = [
                sys.executable, str(script), '--data-dir', str(user_root),
                '--port', '0', '--no-browser',
            ]

            def invoke(*extra, timeout=20):
                return subprocess.run(
                    common_args + list(extra), cwd=repository, env=environment,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=timeout, creationflags=creationflags,
                )

            server_process = subprocess.Popen(
                common_args, cwd=repository, env=environment,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            try:
                deadline = time.monotonic() + 20
                record = None
                data_dir = (user_root / 'exams' / '_studio').resolve()
                while time.monotonic() < deadline:
                    record = desktop._read_record(record_path)
                    if (record and desktop._health(
                            record.get('base_url', ''), runtime.APP_ID,
                            runtime.APP_VERSION, data_dir)):
                        break
                    if server_process.poll() is not None:
                        log = log_path.read_text(encoding='utf-8', errors='replace') if log_path.exists() else ''
                        self.fail(f'launcher exited with {server_process.returncode}: {log[-1500:]}')
                    time.sleep(0.1)
                self.assertIsNotNone(record, 'native launcher did not publish an instance record')
                self.assertTrue(desktop._pid_alive(server_process.pid))
                self.assertEqual(record.get('pid'), server_process.pid)
                self.assertEqual(record.get('install_root'), str(repository))

                reuse = invoke()
                self.assertEqual(reuse.returncode, 0)
                self.assertTrue(desktop._health(record['base_url'], runtime.APP_ID,
                                                runtime.APP_VERSION, data_dir))
                self.assertIn('Reusing verified Question Studio instance',
                              log_path.read_text(encoding='utf-8', errors='replace'))

                stop = invoke('--stop', timeout=25)
                self.assertEqual(stop.returncode, 0)
                server_process.wait(timeout=10)
                self.assertFalse(desktop._pid_alive(server_process.pid))
                self.assertFalse(record_path.exists())
                self.assertFalse((user_root / f'{runtime.APP_ID}.stop-request.json').exists())
                self.assertFalse(list(user_root.glob(f'{runtime.APP_ID}.stop-response-*.json')))

                # Stopping an absent instance is idempotent.
                self.assertEqual(invoke('--stop').returncode, 0)
            finally:
                if server_process.poll() is None:
                    server_process.terminate()
                    server_process.wait(timeout=5)

    def test_default_port_collision_uses_private_ephemeral_port(self):
        with _tempdir() as temporary:
            ready_path = Path(temporary) / 'listener-port.txt'
            listener_script = (
                'import socket, sys, time; '
                's = socket.socket(); '
                's.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); '
                's.bind(("127.0.0.1", 0)); s.listen(); '
                'open(sys.argv[1], "w").write(str(s.getsockname()[1])); '
                'time.sleep(60)'
            )
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            listener_process = subprocess.Popen(
                [sys.executable, '-c', listener_script, str(ready_path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not ready_path.exists():
                    if listener_process.poll() is not None:
                        self.fail(f'port owner exited with {listener_process.returncode}')
                    time.sleep(0.05)
                self.assertTrue(ready_path.exists(), 'port owner did not publish its port')
                occupied_port = int(ready_path.read_text(encoding='ascii'))

                # Treat this temporary occupied port as the default to exercise
                # the exact fallback used for a collision on port 8765.
                with patch.object(desktop, 'DEFAULT_PORT', occupied_port):
                    fallback = desktop._create_server(
                        socketserver.TCPServer,
                        http.server.BaseHTTPRequestHandler,
                        occupied_port,
                    )
                try:
                    self.assertNotEqual(fallback.server_address[1], occupied_port)
                    self.assertTrue(
                        listener_process.poll() is None,
                        'fallback must leave the process owning the requested port running',
                    )
                finally:
                    fallback.server_close()
            finally:
                if listener_process.poll() is None:
                    listener_process.terminate()
                    listener_process.wait(timeout=5)

    def test_stop_refuses_to_shutdown_with_running_jobs(self):
        with _tempdir() as temporary:
            user_root = Path(temporary)
            record = {
                'identity': runtime.APP_ID, 'version': runtime.APP_VERSION,
                'install_root': str(desktop.ROOT), 'data_dir': str(user_root / 'exams' / '_studio'),
                'pid': os.getpid(), 'stop_token': 's' * 48,
            }
            request_id = 'a' * 32
            request_path = user_root / f'{runtime.APP_ID}.stop-request.json'
            desktop._write_record(request_path, {
                **record, 'request_id': request_id,
            })
            class Core:
                LOCK = threading.RLock()

            class Server:
                shutdown_calls = 0

                def shutdown(self):
                    self.shutdown_calls += 1

            server = Server()
            flag = threading.Event()
            status = desktop._handle_stop_request(
                request_path, user_root, record,
                {'job-1': {'status': 'running'}}, server, Core, flag,
            )

            response_path = desktop._stop_response_path(user_root, runtime.APP_ID, request_id)
            response = desktop._read_record(response_path)
            self.assertEqual(status, 'busy')
            self.assertEqual(response.get('status'), 'busy')
            self.assertEqual(server.shutdown_calls, 0)
            self.assertFalse(flag.is_set())
            self.assertFalse(request_path.exists())

    def test_stop_cleans_stale_instance_for_current_install_only(self):
        with _tempdir() as temporary:
            user_root = Path(temporary) / 'user-data'
            data_dir = user_root / 'exams' / '_studio'
            record_path = user_root / f'{runtime.APP_ID}.instance.json'
            request_path = user_root / f'{runtime.APP_ID}.stop-request.json'
            request_id = 'b' * 32
            stale_record = {
                'identity': runtime.APP_ID, 'version': runtime.APP_VERSION,
                'install_root': str(desktop.ROOT), 'data_dir': str(data_dir),
                'pid': 0xFFFFFFFF, 'base_url': 'http://127.0.0.1:65534',
                'stop_token': 't' * 48,
            }
            desktop._write_record(record_path, stale_record)
            desktop._write_record(request_path, {**stale_record, 'request_id': request_id})
            response_path = desktop._stop_response_path(user_root, runtime.APP_ID, request_id)
            desktop._write_record(response_path, {'request_id': request_id,
                                                  'install_root': str(desktop.ROOT),
                                                  'status': 'stopping'})

            with patch.object(runtime, 'user_root', return_value=user_root), \
                    patch('app.core.DATA', data_dir):
                self.assertEqual(desktop._stop(None, runtime), 0)

            self.assertFalse(record_path.exists())
            self.assertFalse(request_path.exists())
            self.assertFalse(response_path.exists())

            other_record = {**stale_record, 'install_root': str(user_root / 'other-install')}
            desktop._write_record(record_path, other_record)
            desktop._write_record(request_path, {**other_record, 'request_id': request_id})
            with patch.object(runtime, 'user_root', return_value=user_root), \
                    patch('app.core.DATA', data_dir):
                self.assertEqual(desktop._stop(None, runtime), 0)
            self.assertTrue(record_path.exists())
            self.assertTrue(request_path.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
