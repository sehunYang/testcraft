import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
from app import core, vectors, images, server
from test_support import cleanup_tempdir
from PIL import Image, ImageDraw, ImageChops
from test_layers import image_card

SOURCE='<svg viewBox="0 0 1000 640"><defs><marker id="tip" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8Z"/></marker></defs><g id="geometry" stroke="black" stroke-width="3" fill="none" transform="translate(10 20)"><rect x="100" y="100" width="200" height="80"/><line x1="100" y1="220" x2="600" y2="220" marker-end="url(#tip)"/></g></svg>'

class VectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=core.ROOT/'.runtime');self.root=Path(self.tmp.name)
        self.patch=patch.object(core,'DATA',self.root/'studio');self.patch.start()
    def tearDown(self):self.patch.stop();cleanup_tempdir(self.tmp)
    def test_svg_preserves_inherited_transform_and_arrow(self):
        # Supply white canvas to both renderings for pixel comparison.
        src=SOURCE.replace('<defs>','<rect width="1000" height="640" fill="white"/><defs>')
        scene=vectors.from_svg(src,'a'*64)
        self.assertEqual(len(scene['objects']),2)
        images.render_svg(src,self.root/'before.png');images.render_svg(vectors.to_svg(scene),self.root/'after.png')
        with Image.open(self.root/'before.png') as a,Image.open(self.root/'after.png') as b:
            self.assertIsNone(ImageChops.difference(a.convert('RGB'),b.convert('RGB')).getbbox())
    def test_raster_holes_and_components(self):
        im=Image.new('RGB',(1000,640),'white');d=ImageDraw.Draw(im);d.rectangle((100,100,300,200),outline='black',width=5);d.rectangle((500,300,600,400),fill='black');im.save(self.root/'r.png')
        scene=vectors.from_raster(self.root/'r.png','a'*64)
        self.assertEqual(len(scene['objects']),2)
        images.render_svg(vectors.to_svg(scene),self.root/'trace.png')
        with Image.open(self.root/'trace.png') as p:
            p=p.resize((1000,640));self.assertEqual(p.getpixel((200,150))[:3],(255,255,255));self.assertEqual(p.getpixel((550,350))[:3],(0,0,0))
    def test_geometry_edits_keep_approval_and_labels_but_change_final(self):
        c=image_card();c['labels_initialized']=True;eid=core.uid();c['image']=server.make_image(eid,c,None,svg=SOURCE)
        old=core.content_hash(c);digest=core.image_final_digest(c);c['image_scene']=vectors.from_svg(SOURCE,c['image']['sha256'])
        c['image_scene']['objects'][0]['matrix']=[1.5,0,0,1,100,0]
        server.save_scene(eid,c);server.finalize_image(eid,c)
        self.assertEqual(core.content_hash(c),old);self.assertNotEqual(core.image_final_digest(c),digest)
        with Image.open(server.asset_path(eid,c['image']['final_file'])) as p:self.assertEqual(p.size,(3000,1920))
        self.assertTrue(server.asset_path(eid,c['image']['file']).exists());self.assertTrue(server.asset_path(eid,c['image']['edited_svg']).exists())
        final=c['image']['final_digest'];c['image_scene']['objects'][0]['visible']=False;self.assertNotEqual(final,core.image_final_digest(c))
    def test_stale_scene_rejected_and_regeneration_preserves_labels(self):
        c=image_card();eid=core.uid();c['image']=server.make_image(eid,c,None,svg=SOURCE);c['image_scene']=vectors.from_svg(SOURCE,'b'*64)
        with self.assertRaisesRegex(ValueError,'원본'):server.save_scene(eid,c)
        c['image_labels']=[dict(id='a'*16,kind='physics',text='v_0',size=28,x=200,y=100,rotation=0)];original=copy.deepcopy(c['image_labels'])
        c['image']=server.make_image(eid,c,None,svg=SOURCE)
        self.assertIsNone(c['image_scene']);self.assertEqual(c['image_labels'],original)
    def test_invalid_or_active_svg_rejected(self):
        for source in ['<script/>','<text>x</text>','<path onclick="bad()"/>','<image href="file:///x"/>','<path fill="url(https://x)"/>','<!DOCTYPE x><path/>','<foreignObject/>']:
            with self.subTest(source=source),self.assertRaises((ValueError,Exception)):vectors.safe_fragment(source)
        scene=vectors.from_svg(SOURCE,'a'*64);scene['objects'][0]['matrix']=[0]*6
        with self.assertRaises(ValueError):vectors.normalize_scene(scene)
    def test_legacy_final_digest_stays_valid(self):
        c=image_card();c['image']={'sha256':'abc'}
        import json
        self.assertEqual(core.image_final_digest(c),hashlib.sha256(json.dumps(['abc',[]],sort_keys=True,ensure_ascii=False).encode()).hexdigest())
    def test_restore_original_restores_original_checks(self):
        c=image_card();eid=core.uid();c['image']=server.make_image(eid,c,None,svg=SOURCE,checks=[{'label':'original','ok':False}]);c['image_scene']=vectors.from_svg(SOURCE,c['image']['sha256']);server.save_scene(eid,c)
        self.assertEqual(c['image']['checks'],[])
        c['image_scene']=None;server.save_scene(eid,c)
        self.assertFalse(c['image']['checks'][0]['ok']);self.assertNotIn('edited_file',c['image'])
    def test_edited_composite_embedded_in_exam(self):
        import base64
        import xml.etree.ElementTree as ET
        c=image_card();c['labels_initialized']=True;c['image_labels']=[dict(id=core.uid(),kind='physics',text='v_0',size=28,x=700,y=300,rotation=0)]
        eid=core.uid();c['image']=server.make_image(eid,c,None,svg=SOURCE);c['image_scene']=vectors.from_svg(SOURCE,c['image']['sha256']);c['image_scene']['objects'][0]['matrix']=[2,0,0,1,0,0]
        server.finalize_image(eid,c);e=core.save_exam(dict(id=eid,title='객체 출력 검증',subject='12역학',cards=[c],exports=[],revision=0,card_approval={'digest':core.cards_digest([c])}))
        bundle=server.export_exam(e);root=ET.parse(core.exam_path(eid)/'exports'/bundle['id']/'시험지_학생용.hml')
        self.assertEqual(base64.b64decode(root.find('.//BINDATA').text),server.asset_path(eid,c['image']['final_file']).read_bytes())

if __name__=='__main__':unittest.main()
