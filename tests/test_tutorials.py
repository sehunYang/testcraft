import io
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
from app import server

STATIC=Path(__file__).resolve().parents[1]/'app/static'
MANIFEST=json.loads((STATIC/'tutorials-manifest.json').read_text(encoding='utf-8'))

def get(path,headers=None):
    class MemoryHandler(server.Handler):
        def __init__(inner):
            inner.path=path;inner.headers={'Host':'127.0.0.1',**(headers or {})}
            inner.rfile=io.BytesIO();inner.wfile=io.BytesIO();inner.status=None;inner.sent={}
        def send_response(inner,status,message=None): inner.status=status
        def send_header(inner,key,value): inner.sent[key]=value
        def end_headers(inner): pass
    handler=MemoryHandler();handler.do_GET();return handler

class TutorialHelpTests(unittest.TestCase):
    def test_manifest_lists_eight_bundled_episodes_in_order(self):
        episodes=MANIFEST['episodes']
        self.assertEqual([e['number'] for e in episodes],list(range(1,9)))
        self.assertEqual(episodes[0]['id'],'00-install')
        for e in episodes:
            with self.subTest(episode=e['id']):
                for key,ext in (('video','mp4'),('captions','vtt'),('poster','jpg')):
                    self.assertRegex(e[key],r'^/tutorials/[0-9]{2}-[a-z-]+\.'+ext+'$')
                    self.assertTrue((STATIC/e[key].lstrip('/')).is_file(),e[key])
                self.assertTrue((STATIC/e['captions'].lstrip('/')).read_text(encoding='utf-8').startswith('WEBVTT'))

    def test_chapters_follow_the_video_and_name_real_controls(self):
        for e in MANIFEST['episodes']:
            chapters=e['chapters']
            with self.subTest(episode=e['id']):
                self.assertEqual(len({c['id'] for c in chapters}),len(chapters))
                for a,b in zip(chapters,chapters[1:]): self.assertAlmostEqual(a['end'],b['start'],places=2)
                self.assertTrue(all(c['start']<c['end']<=e['duration'] for c in chapters))
                for c in chapters:
                    self.assertTrue(c['text'] and c['title'])
                    for t in c['targets']: self.assertTrue(t['selector'].strip() and t['label'].strip())

    def test_video_is_served_in_byte_ranges_for_chapter_seeking(self):
        path=MANIFEST['episodes'][0]['video'];size=(STATIC/path.lstrip('/')).stat().st_size
        h=get(path,{'Range':'bytes=100-199'})
        self.assertEqual((h.status,h.sent['Content-Range'],len(h.wfile.getvalue())),(206,f'bytes 100-199/{size}',100))
        self.assertEqual(h.sent['Content-Type'],'video/mp4');self.assertEqual(h.sent['Accept-Ranges'],'bytes')
        tail=get(path,{'Range':'bytes=-10'})
        self.assertEqual((tail.status,len(tail.wfile.getvalue())),(206,10))
        self.assertEqual(get(path,{'Range':f'bytes={size}-'}).status,416)

    def test_only_named_tutorial_files_are_served(self):
        self.assertEqual(get(MANIFEST['episodes'][1]['captions']).status,200)
        for path in ('/tutorials/../server.py','/tutorials/01-start.exe','/tutorials/99-missing.mp4'):
            with self.subTest(path=path): self.assertEqual(get(path).status,404)

    def test_help_plays_local_files_only(self):
        script=(STATIC/'tutorials.js').read_text(encoding='utf-8')
        self.assertNotIn('releases/download/media-v1',script)
        self.assertIn(r"function safeAsset(value){return typeof value==='string'&&/^\/tutorials\/[0-9]{2}-[a-z-]+\.mp4$/",script)

if __name__=='__main__':unittest.main()
