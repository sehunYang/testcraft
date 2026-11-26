"""창작 요소를 AI 그림 생성 PNG로 만드는 그림(2026-11-26): 요소별 PNG와 한 장 PNG."""
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw     # .runtime/packages 의 PIL보다 먼저(설치된 Python에 맞는 것)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
from app import cli, core, images, server, vectors
from test_support import cleanup_tempdir
from test_layers import image_card

MIXED_SVG=('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 640"><rect width="1000" height="640" fill="white"/>'
           '<g id="geometry"><line data-element="floor" x1="50" y1="500" x2="950" y2="500" stroke="black" stroke-width="3"/></g>'
           '<g id="illustration"><rect data-element="ball" x="400" y="300" width="200" height="200" fill="none" stroke="none"/></g></svg>')


def fake_png(size=(600,400), color=(200,40,40)):
    """흰 바탕에 테두리 있는 색 사각형(안쪽 흰 구멍 포함) — 흑백화·바탕 제거를 확인한다."""
    im=Image.new('RGB',size,'white'); d=ImageDraw.Draw(im)
    d.rectangle((100,80,500,320),outline='black',width=8,fill=color); d.rectangle((250,170,350,230),fill='white')
    b=io.BytesIO(); im.save(b,'PNG'); return b.getvalue()


class RasterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=core.ROOT/'.runtime'); self.root=Path(self.tmp.name)
        self.patch=patch.object(core,'DATA',self.root/'studio'); self.patch.start()
    def tearDown(self): self.patch.stop(); cleanup_tempdir(self.tmp)

    def test_field_defaults_and_validation(self):
        c=image_card('mixed')
        self.assertEqual(core.normalize_raster(None),'')
        with self.assertRaises(ValueError): core.normalize_raster('photo')
        c['image_raster']='elements'; self.assertEqual(core.raster_mode(c),'elements')
        self.assertFalse(core.image_plan_errors(c))
        s=image_card('strict'); s['image_raster']='whole'
        self.assertEqual(core.raster_mode(s),'')
        self.assertTrue(any('strict' in e for e in core.image_plan_errors(s)))
        f=image_card('flexible'); f['image_creative']='손수레를 미는 학생'; f['image_raster']='elements'
        self.assertTrue(any('요소ID' in e for e in core.image_plan_errors(f)))
        f['image_raster']='whole'; self.assertFalse(core.image_plan_errors(f))

    def test_method_change_keeps_card_approval_but_resets_plan(self):
        c=image_card('mixed'); before=core.content_hash(c); plan=core.image_plan_context(c); ctx=core.image_context(c)
        c['image_raster']=''; self.assertEqual(core.image_context(c),ctx)   # 빈 값은 예전 그림 승인을 바꾸지 않는다
        c['image_raster']='elements'
        self.assertEqual(core.content_hash(c),before)
        self.assertNotEqual(core.image_plan_context(c),plan)
        self.assertIn('PNG',core.image_prompt(c))

    def test_material_block_keeps_method(self):
        c=image_card('mixed'); c['image_raster']='whole'
        c['materials']=[{'id':c['id'],'kind':'image','label':'','content':'그림',**{k:copy.deepcopy(c.get(k)) for k in core.MATERIAL_IMAGE_FIELDS}}]
        core.normalize_materials(c)
        self.assertEqual(c['materials'][0]['image_raster'],'whole')
        projected,_=core.material_projection(c,c['id'],require_image=True)
        self.assertEqual(projected['image_raster'],'whole')
        c['materials'][0]['image_raster']='bad'
        with self.assertRaises(ValueError): core.normalize_materials(c)

    def test_prepare_raster_grayscale_transparent_background(self):
        png,w,h=images.prepare_raster(fake_png())
        with Image.open(io.BytesIO(png)) as im:
            self.assertEqual(im.mode,'LA'); self.assertEqual((im.width,im.height),(w,h))
            self.assertLess(w,600); self.assertLess(h,400)                      # 여백을 잘랐다
            self.assertEqual(im.getpixel((0,0))[1],0)                           # 둘레 바탕은 투명
            cx,cy=w//2,h//2
            self.assertEqual(im.getpixel((cx,cy)),(255,255))                    # 안쪽 흰 구멍은 흰색 그대로, 불투명
            gray=im.getpixel((cx-90,cy))[0]
            self.assertTrue(0<gray<255)                                         # 색은 회색으로
        dw,dh,m=images.fit_box(w,h,(100,100,300,300))
        self.assertAlmostEqual(dw,300,delta=.01); self.assertLessEqual(dh,300); self.assertAlmostEqual(m[5],100+(300-dh)/2,delta=.01)

    def test_scene_with_png_element_renders_and_survives_normalize(self):
        png,w,h=images.prepare_raster(fake_png())
        obj=dict(id='c'*16,name='ball (PNG)',svg='',raster='d'*16+'.png',width=200,height=150,matrix=[1,0,0,1,400,320],visible=True,locked=False)
        scene=vectors.from_svg(MIXED_SVG,'a'*64,{'ball':obj})
        self.assertEqual([o.get('raster') for o in scene['objects']],[None,'d'*16+'.png'])
        self.assertEqual(vectors.normalize_scene(scene),scene)
        with self.assertRaises(ValueError): vectors.normalize_scene(dict(scene,objects=[dict(obj,raster='../x.png')]))
        with self.assertRaises(ValueError): vectors.normalize_scene(dict(scene,objects=[dict(obj,svg='<path d="M0 0"/>')]))
        svg=vectors.to_svg(scene,lambda name:png)
        with self.assertRaises(ValueError): images.validate_svg(svg)              # AI SVG에는 그림 요소를 허용하지 않는다
        images.render_svg(svg,self.root/'out.png',allow_raster=True)
        with Image.open(self.root/'out.png') as out:
            out=out.convert('L').resize((1000,640))
            self.assertLess(out.getpixel((500,500)),100)                        # 고정 요소(바닥선)는 그대로
            self.assertLess(out.crop((400,320,600,470)).getextrema()[0],120)     # PNG 요소가 자리에 들어감
        with self.assertRaises(ValueError): images.validate_svg(svg.replace('data:image/png','data:image/svg+xml'),allow_raster=True)

    def run_raster(self, card, svg, calls):
        def fake(provider,folder,prompt,model='',cancel=None):
            calls.append(prompt); return fake_png()
        eid=core.uid()
        with patch.object(cli,'generate_png',side_effect=fake):
            card['image']=server.make_raster_image(eid,card,svg,'codex','',None,self.root/'job')
        return eid

    def test_mixed_elements_build_editable_scene_and_final_image(self):
        c=image_card('mixed'); c['image_raster']='elements'; calls=[]
        eid=self.run_raster(c,MIXED_SVG,calls)
        self.assertEqual(len(calls),1); self.assertIn('공 외관',calls[0]); self.assertIn('floor',calls[0]); self.assertIn('글씨',calls[0])
        im=c['image']; scene=c['image_scene']
        self.assertEqual(scene['source_sha'],im['sha256']); self.assertEqual(im['raster']['mode'],'elements')
        raster=[o for o in scene['objects'] if o.get('raster')]
        self.assertEqual(len(raster),1); self.assertTrue(server.asset_path(eid,raster[0]['raster']).is_file())
        self.assertNotIn('data:image',server.asset_path(eid,im['svg']).read_text(encoding='utf-8'))
        # 교사가 PNG 요소를 옮기고 키운 뒤 확정하면 최종 그림에 반영된다
        raster[0]['matrix']=[1.5,0,0,1.5,50,50]
        c['labels_initialized']=True; c['image_labels']=[]
        server.save_scene(eid,c); server.finalize_image(eid,c)
        self.assertTrue(c['image']['approved']); self.assertTrue(server.asset_path(eid,c['image']['final_file']).is_file())
        # 원본으로 되돌렸다가 다시 객체로 바꾸면 PNG 요소가 든 처음 장면이 돌아온다
        self.assertEqual(copy.deepcopy(im['raster']['scene'])['objects'][-1]['raster'],raster[0]['raster'])

    def test_whole_png_for_flexible_uses_one_generation(self):
        c=image_card('flexible'); c['image_creative']='학생이 손수레를 미는 모습'; c['image_raster']='whole'; calls=[]
        self.run_raster(c,images.WHOLE_PLACEHOLDER,calls)
        self.assertEqual(len(calls),1); self.assertIn('한 장면',calls[0]); self.assertIn('가로로 긴',calls[0])
        self.assertEqual(sum(1 for o in c['image_scene']['objects'] if o.get('raster')),1)
        self.assertEqual(c['image']['raster']['mode'],'whole')

    def test_mixed_whole_places_one_png_over_all_boxes(self):
        c=image_card('mixed'); c['image_creative']='cart: 손수레\nkid: 학생'; c['image_raster']='whole'; calls=[]
        svg=MIXED_SVG.replace('<rect data-element="ball" x="400" y="300" width="200" height="200" fill="none" stroke="none"/>',
                              '<rect data-element="cart" x="400" y="380" width="300" height="120" fill="none"/><rect data-element="kid" x="200" y="200" width="150" height="300" fill="none"/>')
        self.run_raster(c,svg,calls)
        self.assertEqual(len(calls),1); self.assertIn('cart:',calls[0]); self.assertIn('배치',calls[0])
        raster=[o for o in c['image_scene']['objects'] if o.get('raster')]
        self.assertEqual(len(raster),1)
        self.assertGreaterEqual(raster[0]['matrix'][4],200-.01)

    def test_missing_box_is_reported(self):
        c=image_card('flexible'); c['image_creative']='cart: 손수레\nkid: 학생'; c['image_raster']='elements'
        svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 640"><g id="illustration"><rect data-element="cart" x="10" y="10" width="100" height="100" fill="none"/></g></svg>'
        with self.assertRaisesRegex(ValueError,'kid'): self.run_raster(c,svg,[])

    def test_view_and_tilt(self):
        # 2D 옆모습 도식과 시점을 맞추고, 기울기는 앱이 정확히 돌린다(2026-11-26 교사 지적)
        c=image_card('mixed'); c['image_raster']='elements'
        flat=cli.raster_prompt(c,'ball','공',(0,0,200,100))
        self.assertIn('정사영',flat); self.assertIn('쿼터뷰',flat); self.assertIn('같은 시점',flat); self.assertNotIn('기울이지 않는다',flat)
        self.assertIn('기울이지 않는다',cli.raster_prompt(c,'ball','공',(0,0,200,100),angle=25))
        self.assertIn('data-angle',cli.prompt_for(c,'image'))
        svg=MIXED_SVG.replace('fill="none" stroke="none"/>','fill="none" stroke="none" data-angle="25"/>')
        self.assertEqual(images.placeholder_angles(svg),{'ball':25.0})
        self.assertEqual(images.placeholder_angles(MIXED_SVG),{})
        dw,dh,m=images.fit_box(200,100,(100,100,400,400),bottom=True)
        self.assertEqual((dw,dh),(400,200)); self.assertEqual(m,[1,0,0,1,100,300])     # 아래 변에 붙는다
        import math
        dw,dh,m=images.fit_box(200,100,(100,100,400,200),angle=30)
        a,b,c_,d,e,f=m
        self.assertAlmostEqual(a,math.cos(math.radians(30)),5); self.assertAlmostEqual(b,math.sin(math.radians(30)),5)
        centre=(a*dw/2+c_*dh/2+e,b*dw/2+d*dh/2+f)                                  # 그림 가운데는 상자 가운데 그대로
        self.assertAlmostEqual(centre[0],300,2); self.assertAlmostEqual(centre[1],200,2)

    def test_tilted_element_is_rotated_in_scene(self):
        c=image_card('mixed'); c['image_raster']='elements'; calls=[]
        svg=MIXED_SVG.replace('fill="none" stroke="none"/>','fill="none" stroke="none" data-angle="20"/>')
        self.run_raster(c,svg,calls)
        self.assertIn('기울이지 않는다',calls[0])
        m=[o for o in c['image_scene']['objects'] if o.get('raster')][0]['matrix']
        self.assertGreater(m[1],0.3)                                                     # 돌아가 있다

    def test_generate_png_reads_codex_generated_images(self):
        home=self.root/'codex'; folder=self.root/'step'
        def fake_execute(provider,folder_,prompt,schema,model='',cancel=None,images=()):
            folder_.mkdir(parents=True,exist_ok=True)
            (folder_/'events.log').write_text(json.dumps({'type':'thread.started','thread_id':'01a2-thread-abcd'})+'\n',encoding='utf-8')
            out=home/'generated_images'/'01a2-thread-abcd'; out.mkdir(parents=True,exist_ok=True)
            (out/'exec-1.png').write_bytes(b'PNGDATA')
            return {'note':'ok'}
        with patch.object(cli,'execute',side_effect=fake_execute), patch.dict('os.environ',{'CODEX_HOME':str(home)}), patch.object(cli.runtime,'installed_mode',return_value=False):
            self.assertEqual(cli.generate_png('codex',folder,'그림'),b'PNGDATA')
        with self.assertRaisesRegex(ValueError,'Codex'): cli.generate_png('claude',folder,'그림')

    def test_prompts_and_schemas(self):
        c=image_card('mixed'); c['image_raster']='elements'
        prompt=cli.prompt_for(c,'image')
        self.assertIn('자리 상자',prompt)
        c['image_raster']=''; self.assertNotIn('자리 상자',cli.prompt_for(c,'image'))
        for schema in (cli.schema_for('plan'),cli.QUESTION_SCHEMA,cli.MATERIAL_SCHEMA):
            self.assertIn('image_raster',schema['required'])
        self.assertIn('image_raster',cli.IMAGE_POLICY)


if __name__=='__main__': unittest.main()
