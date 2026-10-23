"""Build the public GitHub Pages directory and validate release download metadata.

Copies only docs/ and reads the latest public release at build time. Never copies
the application, teacher data, runtime dependencies, or credentials to Pages.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'sehunYang/testcraft'


def release_snapshot(release: dict) -> dict:
    tag = release.get('tag_name', '')
    if release.get('draft') or release.get('prerelease') or not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise ValueError('A published stable TestCraft release is required.')
    version = tag[1:]
    prefix = f'https://github.com/{REPOSITORY}/releases/download/{tag}/'
    names = {'setup': f'TestCraft-{version}-windows-x64-setup.exe',
             'portable': f'TestCraft-{version}-windows-x64-portable.zip',
             'checksums': 'SHA256SUMS'}
    assets = []
    for kind, name in names.items():
        matches = [item for item in release.get('assets', []) if item.get('name') == name]
        if len(matches) != 1:
            raise ValueError(f'Missing or duplicate release asset: {name}')
        item = matches[0]
        if item.get('browser_download_url') != prefix + name or not isinstance(item.get('size'), int) or item['size'] <= 0:
            raise ValueError(f'Invalid download metadata: {name}')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', item.get('digest', '')):
            raise ValueError(f'Asset checksum is required: {name}')
        assets.append({'kind': kind, 'name': name, 'url': prefix + name,
                       'size': item['size'], 'digest': item['digest']})
    return {'version': tag, 'published_at': release.get('published_at', ''), 'assets': assets}


def build(destination: Path, release: Path | None = None) -> None:
    source = (ROOT / 'docs').resolve()
    destination = destination.resolve()
    if destination == ROOT or destination in source.parents or source == destination or source in destination.parents:
        raise ValueError('Choose a separate build destination outside docs/.')
    # No recursive cleanup: the output directory must start empty.
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Build destination must be empty.')
    shutil.copytree(source, destination, dirs_exist_ok=True)
    if release:
        snapshot = release_snapshot(json.loads(release.read_text(encoding='utf-8-sig')))
        (destination / 'release.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (destination / '.nojekyll').touch()
    print(f'GitHub Pages files prepared: {destination}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--release-json', type=Path)
    args = parser.parse_args()
    build(args.output, args.release_json)
