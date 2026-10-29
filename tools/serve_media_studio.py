"""An isolated, real TestCraft instance for recording fictional examples.

No mocked AI, authentication, export or approval. Never opens teachers' projects.
"""
import json
import os
from pathlib import Path
import sys
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.runtime/packages')]
from app import core, server, labels

workspace = ROOT / '.runtime/media-production'
workspace.mkdir(parents=True, exist_ok=True)
core.DATA = workspace / 'exams'
core.DATA.mkdir(exist_ok=True)
labels.CACHE = workspace / 'label-cache'
labels.CACHE.mkdir(exist_ok=True)
http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
(workspace / 'server.json').write_text(json.dumps({
    'pid': os.getpid(), 'url': f'http://127.0.0.1:{http.server_port}',
    'data_dir': str(core.DATA), 'ai': 'real-codex-cli'
}), encoding='utf-8')
http.serve_forever()
