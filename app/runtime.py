"""Installed and source-checkout runtime paths for TestCraft."""
from pathlib import Path
import os
import shutil


# Stable installation/IPC identity preserves upgrades and existing running-instance records.
APP_ID = 'question-studio'
APP_NAME = 'TestCraft'
APP_VERSION = '1.1.1'


def is_installed():
    return os.environ.get('QUESTION_STUDIO_INSTALLED') == '1'


def installed_mode():
    """Compatibility name shared with the desktop bootstrap and Codex setup."""
    return is_installed()


def user_root(source_root=None):
    """Return the per-user writable root, honoring the smoke-test override."""
    override = os.environ.get('QUESTION_STUDIO_DATA_DIR', '').strip()
    if override:
        return Path(override).expanduser().resolve()
    if not is_installed():
        return (Path(source_root).resolve() if source_root else Path.cwd().resolve()) / '.runtime'

    # Keep data from Question Studio installs in place. A clean TestCraft
    # profile gets the new branded directory, while an existing legacy root
    # remains authoritative until the user explicitly moves that data.
    local_app_data = os.environ.get('LOCALAPPDATA', '').strip()
    if local_app_data:
        base = Path(local_app_data).expanduser().resolve()
    elif os.name == 'nt':
        base = Path.home() / 'AppData' / 'Local'
    else:
        base = Path.home() / '.local' / 'share'
    legacy_root = base / 'QuestionStudio'
    if legacy_root.exists():
        return legacy_root
    return base / APP_NAME


def data_dir(source_root):
    source_root = Path(source_root).resolve()
    if is_installed() or os.environ.get('QUESTION_STUDIO_DATA_DIR', '').strip():
        return user_root(source_root) / 'exams' / '_studio'
    return source_root / 'exams' / '_studio'


def label_cache_dir(source_root):
    source_root = Path(source_root).resolve()
    if is_installed() or os.environ.get('QUESTION_STUDIO_DATA_DIR', '').strip():
        return user_root(source_root) / 'cache' / 'labels-v2'
    return source_root / '.runtime' / 'labels-v2'


def log_dir(source_root):
    return user_root(source_root) / 'logs'


def codex_home(source_root=None):
    return user_root(source_root) / 'codex-home'


_API_CREDENTIAL_ENV = (
    'OPENAI_API_KEY', 'OPENAI_ADMIN_KEY', 'OPENAI_ACCESS_TOKEN', 'CODEX_API_KEY',
    'CODEX_ACCESS_TOKEN', 'AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_KEY',
    'OPENAI_BASE_URL', 'OPENAI_API_BASE',
    'OPENAI_FEDERATION_RULE_ID', 'OPENAI_IDENTITY_TOKEN_FILE',
    'OPENAI_WORKLOAD_IDENTITY_CONTEXT',
    'CODEX_EXEC_SERVER_NOISE_AUTH_TOKEN', 'CODEX_GUARDIAN_DECISIONS_API_KEY',
    'NODE_REPL_AUTH_TOKEN',
)


def codex_environment(source_root=None, environ=None, executable=None):
    """Use the app's isolated ChatGPT OAuth home and drop API-key credentials."""
    env = dict(os.environ if environ is None else environ)
    for key in _API_CREDENTIAL_ENV:
        env.pop(key, None)
    env['CODEX_HOME'] = str(codex_home(source_root))
    if executable:
        binary_dir = str(Path(executable).resolve().parent)
        path_parts = env.get('PATH', '').split(os.pathsep) if env.get('PATH') else []
        if not any(os.path.normcase(part) == os.path.normcase(binary_dir) for part in path_parts):
            env['PATH'] = binary_dir + (os.pathsep + env['PATH'] if env.get('PATH') else '')
    return env


def bundled_node(source_root):
    """Return the bundled Node executable if present in this install tree."""
    path = Path(source_root).resolve() / 'runtime' / 'node' / 'node.exe'
    return path if path.is_file() else None


def node_executable(source_root):
    """Prefer the install's Node runtime; source checkouts may use PATH."""
    path = bundled_node(source_root)
    if path:
        return str(path)
    return shutil.which('node.exe') or shutil.which('node')


def node_environment(source_root, environ=None):
    """Prepare module lookup for bundled sharp without relying on Codex caches."""
    env = dict(os.environ if environ is None else environ)
    root = Path(source_root).resolve()
    node = bundled_node(root)
    if node:
        modules = str(root / 'node_modules')
        prior = env.get('NODE_PATH', '')
        env['NODE_PATH'] = modules + (os.pathsep + prior if prior else '')
        node_dir = str(node.parent)
        path_parts = env.get('PATH', '').split(os.pathsep) if env.get('PATH') else []
        if node_dir not in path_parts:
            env['PATH'] = node_dir + (os.pathsep + env['PATH'] if env.get('PATH') else '')
    return env
