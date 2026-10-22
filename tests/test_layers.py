import copy
import io
import sys
import tempfile
import unittest
import base64
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
from app import core,images,server,cli,labels
from test_support import cleanup_tempdir
import test_authoring
from test_workflow import card
from PIL import Image

def image_card(mode='strict'):
    c=card();c.update(data_kind='image',image_mode=mode,image_locked='floor: 水平線' if mode!='flexible' else '',image_creative='ball: 공 외관' if mode!='strict' else '',image_text_physics='v_0: 공 위',image_text_math=r'E=\frac{1}{2}mv^2: 오른쪽',image_text_korean='바닥 아래 수평면')
    c['image_plan_approval']={'context':core.image_plan_context(c)}
    return c

class LayerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=core.ROOT/'.runtime')
        self.patch=patch.object(core,'DATA',Path(self.tmp.name)/'studio');self.patch.start()
    def tearDown(self):self.patch.stop();cleanup_tempdir(self.tmp)
    def test_strict_flexible_empty_fields(self):
        c=image_card();self.assertFalse(core.image_plan_errors(c))
        c['image_creative']='없음';self.assertTrue(core.image_plan_errors(c))
        c=image_card('flexible');self.assertFalse(core.image_plan_errors(c))
        c['image_locked']='라벨';self.assertTrue(core.image_plan_errors(c))
    def test_mixed_disjoint_elements(self):
        c=image_card('mixed');self.assertFalse(core.image_plan_errors(c))
        c['image_creative']='floor: 바닥 외관';self.assertTrue(core.image_plan_errors(c))
        c['image_creative']='적당한 창작';self.assertTrue(core.image_plan_errors(c))
    def test_base_prompt_does_not_include_labels_or_legacy_material(self):
        c=image_card();c['material']='LEGACY: 속도 30m/s 글씨를 쓰세요.'
        p=cli.prompt_for(c,'image')
        self.assertNotIn('LEGACY',p);self.assertNotIn('v_0: 공 위',p)
        self.assertNotIn('[창작 허용 영역]',core.image_prompt(c))
        self.assertNotIn('[SVG 규칙]',core.image_prompt(image_card('flexible')))
        lp=cli.prompt_for(c,'labels');self.assertIn('v_0: 공 위',lp)
    def test_reject_embedded_text_and_wrong_layers(self):
        svg='<svg viewBox="0 0 1000 640"><g id="geometry"><text x="1">v</text></g></svg>'
        with self.assertRaisesRegex(ValueError,'글씨'):images.validate_mode_layers(svg,'strict')
        with self.assertRaises(ValueError):images.validate_mode_layers(svg.replace('<text x="1">v</text>',''),'flexible')
        c=image_card('mixed');svg='<svg viewBox="0 0 1000 640"><g id="geometry"><g data-element="floor"/></g><g id="illustration"><g data-element="ball"/></g></svg>'
        images.validate_mode_layers(svg,'mixed',c)
        with self.assertRaises(ValueError):images.validate_mode_layers(svg.replace('data-element="ball"','data-element="floor"'),'mixed',c)
    def test_label_edit_preserves_card_approval_but_invalidates_final(self):
        c=image_card();digest=core.cards_digest([c]);before=core.image_final_digest(c)
        c['image_labels']=[dict(id=core.uid(),kind='physics',text='v_0',x=100,y=100,size=28,rotation=0)];c['labels_initialized']=True
        self.assertEqual(digest,core.cards_digest([c]));self.assertNotEqual(before,core.image_final_digest(c))
    def test_regeneration_preserves_labels_and_deleted_objects(self):
        c=image_card();c['image_labels']=[dict(id=core.uid(),kind='physics',text='v_0',x=100,y=100,size=28,rotation=0)];c['labels_initialized']=True
        e=core.save_exam(dict(id=core.uid(),title='시험',subject='12역학',cards=[c],exports=[],revision=0,card_approval={'digest':core.cards_digest([c])}))
        original=copy.deepcopy(c['image_labels'])
        svg='<svg viewBox="0 0 1000 640"><g id="geometry"><path d="M 100 400 H 900" stroke="black"/></g></svg>'
        with patch.object(cli,'discover',return_value='fixture'),patch.object(cli,'execute',return_value={'svg':svg,'constraints':[]}) as execute:
            job=server.launch_job(e['id'],{'action':'image'});test_authoring.AuthoringTests.wait_job(self,job)
            self.assertEqual(job['status'],'completed');self.assertEqual(execute.call_count,1)
        saved=core.read_exam(e['id'])['cards'][0];self.assertEqual(saved['image_labels'],original)
        server.finalize_image(e['id'],saved);self.assertTrue(saved['image']['approved'])
        final=server.asset_path(e['id'],saved['image']['final_file'])
        with Image.open(final) as im:self.assertEqual(im.size,(3000,1920))
        e['cards']=[saved];bundle=server.export_exam(e,convert_hwpx=False)
        hml=ET.parse(core.exam_path(e['id'])/'exports'/bundle['id']/'시험지_학생용.hml')
        self.assertEqual(base64.b64decode(hml.find('.//BINDATA').text),final.read_bytes())
    def test_first_image_automatically_creates_independent_text(self):
        c=image_card();e=core.save_exam(dict(id=core.uid(),title='시험',subject='12역학',cards=[c],exports=[],revision=0,card_approval={'digest':core.cards_digest([c])}))
        pic={'svg':'<svg viewBox="0 0 1000 640"><g id="geometry"/></svg>','constraints':[]}
        label=dict(kind='physics',text='v_0',x=100,y=100,size=28,rotation=0)
        with patch.object(cli,'discover',return_value='fixture'),patch.object(cli,'execute',side_effect=[pic,{'labels':[label]}]):
            job=server.launch_job(e['id'],{'action':'image'});test_authoring.AuthoringTests.wait_job(self,job)
        saved=core.read_exam(e['id'])['cards'][0]
        self.assertTrue(saved['labels_initialized']);self.assertEqual(len(saved['image_labels']),1)
        self.assertEqual(saved['image_labels'][0]['text'],'v_0');self.assertFalse(saved['image']['approved'])
    def test_math_font_and_malformed_labels(self):
        info=labels.render('math',r'\frac{1}{2}mv^2',32);self.assertEqual(info['font'],'Latin Modern Math')
        self.assertTrue((labels.CACHE/(info['key']+'.png')).exists())
        with self.assertRaises(ValueError):labels.normalize_labels([dict(id=core.uid(),kind='math',text='x',x=float('nan'),y=0,size=28,rotation=0)])
    def test_text_failure_keeps_background_retryable(self):
        c=image_card();e=core.save_exam(dict(id=core.uid(),title='시험',subject='12역학',cards=[c],exports=[],revision=0,card_approval={'digest':core.cards_digest([c])}))
        pic={'svg':'<svg viewBox="0 0 1000 640"><g id="geometry"/></svg>','constraints':[]}
        with patch.object(cli,'discover',return_value='fixture'),patch.object(cli,'execute',side_effect=[pic,ValueError('글씨 생성 실패')]):
            job=server.launch_job(e['id'],{'action':'image'});test_authoring.AuthoringTests.wait_job(self,job)
        saved=core.read_exam(e['id'])['cards'][0];self.assertIsNotNone(saved['image']);self.assertFalse(saved['labels_initialized'])
        with self.assertRaises(ValueError):server.finalize_image(e['id'],saved)
    def test_xlsx_roundtrip_text_prompts_and_objects(self):
        c=image_card();c['image_labels']=[dict(id=core.uid(),kind='physics',text='v_0',x=100,y=100,size=28,rotation=0)]
        c['labels_initialized']=True
        path=Path(self.tmp.name)/'labels.xlsx';core.export_xlsx([c],path)
        restored=core.import_cards(path.read_bytes())[0]
        for key in ('image_labels','image_text_physics','image_text_math','image_text_korean','labels_initialized','image_plan_version'):self.assertEqual(restored[key],c[key])

    def test_layer_metadata_roundtrip_and_hidden_export(self):
        obj=dict(id=core.uid(),kind='physics',text='v_0',x=100,y=100,size=28,rotation=0,name='속도',locked=True,visible=False)
        self.assertEqual(labels.normalize_labels([obj]),[obj])
        c=image_card();c['image_labels']=[obj]
        path=Path(self.tmp.name)/'layers.xlsx';core.export_xlsx([c],path)
        self.assertEqual(core.import_cards(path.read_bytes())[0]['image_labels'],[obj])
        base=Path(self.tmp.name)/'base.png';output=Path(self.tmp.name)/'final.png'
        Image.new('RGB',(1000,640),'white').save(base)
        with patch.object(labels,'render',side_effect=AssertionError('hidden text must not render')):
            labels.compose(base,[obj],output)
        with Image.open(output) as im:self.assertEqual(im.getextrema(),((255,255),(255,255),(255,255)))

if __name__=='__main__':unittest.main(verbosity=2)
