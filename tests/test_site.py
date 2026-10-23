"""The public download guide must only advertise verified stable release files."""
import copy
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from tools.build_site import ROOT, build, release_snapshot


class SiteTests(unittest.TestCase):
    def release(self):
        snapshot = json.loads((ROOT / 'docs/release.json').read_text(encoding='utf-8'))
        return {'tag_name': snapshot['version'], 'draft': False, 'prerelease': False,
                'assets': [{**asset, 'browser_download_url': asset['url']} for asset in snapshot['assets']]}

    def test_release_rejects_broken_or_untrusted_downloads(self):
        release = self.release()
        self.assertEqual(release_snapshot(release)['version'], release['tag_name'])
        for modification in ('draft', 'missing', 'duplicate', 'external', 'checksum'):
            candidate = copy.deepcopy(release)
            if modification == 'draft': candidate['draft'] = True
            if modification == 'missing': candidate['assets'].pop()
            if modification == 'duplicate': candidate['assets'].append(candidate['assets'][0])
            if modification == 'external': candidate['assets'][0]['browser_download_url'] = 'https://example.com/setup.exe'
            if modification == 'checksum': candidate['assets'][0].pop('digest')
            with self.subTest(modification=modification), self.assertRaises(ValueError):
                release_snapshot(candidate)

    def test_static_build_has_no_app_or_teacher_data(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'site'
            build(output)
            self.assertTrue((output / 'index.html').is_file())
            self.assertTrue((output / '.nojekyll').is_file())
            self.assertFalse(any(path.name in {'app', 'exams', 'auth.json', 'TestCraft.exe'} for path in output.rglob('*')))
            with self.assertRaises(ValueError): build(output)

    def test_assets_and_navigation_targets_exist(self):
        class Links(HTMLParser):
            def __init__(self): super().__init__(); self.ids = set(); self.targets = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if attrs.get('id'): self.ids.add(attrs['id'])
                for key in ('href', 'src', 'aria-controls'):
                    if attrs.get(key): self.targets.append((key, attrs[key]))
        page = Links(); page.feed((ROOT / 'docs/index.html').read_text(encoding='utf-8'))
        for key, target in page.targets:
            if key == 'aria-controls': self.assertIn(target, page.ids)
            elif target.startswith('#') and len(target) > 1: self.assertIn(target[1:], page.ids)
            elif target.startswith('./'): self.assertTrue((ROOT / 'docs' / target[2:]).is_file(), target)


if __name__ == '__main__': unittest.main()
