import base64
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
from app import core, images, cli, server
from test_support import cleanup_tempdir
from PIL import Image

def card(kind='단일 정답형', no=1):
    c=core.blank_card(no)
    c.update(standard='[12역학01-01]',standard_name='운동',difficulty='하',type=kind,idea='등속 운동의 이동 거리를 계산한다.',points='100',stem='속력이 2 m/s인 물체가 3초 동안 등속 운동한다.',question='이동 거리는?',choices='① 2 m\n② 3 m\n③ 4 m\n④ 5 m\n⑤ 6 m',answer=5,explanation='이동 거리는 속력과 시간의 곱이므로 6 m이다.',concepts='속력, 이동 거리',calculation=True,checks=[{'label':'이동 거리','lhs':'2*3','rhs':'6'}],review_approved=True)
    return c

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=core.ROOT)
        self.patch=patch.object(core,'DATA',Path(self.tmp.name));self.patch.start()
    def tearDown(self):
        self.patch.stop();cleanup_tempdir(self.tmp)
    def exam(self,cards):
        return core.save_exam({'id':core.uid(),'title':'통합 검증 시험','cards':cards,'exports':[],'revision':0,'card_approval':{'digest':core.cards_digest(cards)}})
    def test_legacy_import(self):
        source=next((core.ROOT/'exams').glob('*/02_card/*.xlsx'),None)
        if source is None:self.skipTest('Private past exams are not distributed.')
        cards=core.import_cards(source.read_bytes())
        self.assertEqual(len(cards),24)
        self.assertTrue(all(c['type'] in core.TYPES for c in cards))
        self.assertTrue(any('기존 유형' in c['review_note'] for c in cards))
    def test_blank_template_not_real_questions(self):
        with self.assertRaises(ValueError):core.import_cards(core.TEMPLATE.read_bytes())
    def test_four_types(self):
        for kind in core.TYPES:self.assertEqual(core.normalize(card(kind),1)['type'],kind)
        with self.assertRaises(ValueError):core.normalize(card('객관식'),1)
    def test_points_preserved(self):
        c=card();c['points']='4.0'
        self.assertEqual(core.normalize(c,1)['points'],'4.0')
    def test_xlsx_round_trip_preserves_template(self):
        path=Path(self.tmp.name)/'card.xlsx'
        c=card();core.export_xlsx([c],path)
        loaded=core.import_cards(path.read_bytes())
        self.assertEqual(len(loaded),1)
        self.assertEqual(loaded[0]['points'],'100')
        self.assertEqual(loaded[0]['explanation'],c['explanation'])
        with zipfile.ZipFile(core.TEMPLATE) as a, zipfile.ZipFile(path) as b:
            self.assertEqual(a.read('xl/worksheets/sheet2.xml'),b.read('xl/worksheets/sheet2.xml'))
    def test_safe_sympy(self):
        self.assertTrue(core.verify_checks([{'lhs':'sqrt(3)**2','rhs':'3'}])[0]['ok'])
        self.assertFalse(core.verify_checks([{'lhs':'2+2','rhs':'5'}])[0]['ok'])
        for bad in ["__import__('os').system('echo test')",'x.__class__','2**1000000','sqrt(x,y)']:
            with self.assertRaises((ValueError,TypeError)): core.safe_expr(bad)
    def test_review_gate(self):
        e=self.exam([card()]);self.assertTrue(core.validate(e)['ready'])
        e['cards'][0]['review_approved']=False
        with self.assertRaises(ValueError):server.export_exam(e)
    def test_calculation_gate(self):
        c=card();c['checks']=[]
        self.assertFalse(core.validate(self.exam([c]))['ready'])
    def test_ratio_gate(self):
        c=card('합답형');c['statements']='ㄱ. 참이다.'
        self.assertFalse(core.validate(self.exam([c]))['ready'])
    def test_image_stale_gate(self):
        c=card();c.update(data_kind='image',image={'approved':True,'context':core.image_context(c)})
        self.assertFalse(core.validate(self.exam([c]))['ready'])
    def test_svg_security(self):
        for body in ['<script>alert(1)</script>','<image href="file:///secret"/>','<rect onclick="x()"/>','<rect fill="url(https://x)"/>']:
            with self.assertRaises(ValueError):images.validate_svg('<svg viewBox="0 0 100 100">'+body+'</svg>')
    def test_render_svg(self):
        path=Path(self.tmp.name)/'image.png'
        images.render_svg('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 640"><rect width="1000" height="640" fill="white"/><circle cx="500" cy="320" r="100" fill="none" stroke="black"/></svg>',path)
        self.assertTrue(path.exists())
        with Image.open(path) as rendered:
            self.assertGreater(rendered.width,1000)
    def test_export_hml_png_answers(self):
        c=card();c.update(data_kind='image',material='수평면의 물체와 속도 화살표',image_mode='strict',image_locked='수평면, 물체 한 개, 오른쪽 속도 화살표',image_creative='',image_text_none=True)
        c['image_plan_approval']={'context':core.image_plan_context(c)}
        e=self.exam([c]);buf=io.BytesIO();Image.new('RGB',(400,240),'white').save(buf,format='PNG')
        c['image']=server.make_image(e['id'],c,buf.getvalue());c['labels_initialized']=True;server.finalize_image(e['id'],c)
        e['cards']=[c];b=server.export_exam(e,convert_hwpx=False);folder=core.exam_path(e['id'])/'exports'/b['id']
        s=ET.parse(folder/'시험지_학생용.hml').getroot();t=ET.parse(folder/'시험지_교사용.hml').getroot()
        self.assertEqual(len(list(s.iter('PICTURE'))),1)
        self.assertEqual(len(list(s.iter('MARKPENBEGIN'))),0)
        self.assertEqual(len(list(t.iter('MARKPENBEGIN'))),1)
        self.assertIn('통합 검증 시험',''.join(s.itertext()))
        self.assertNotIn('프롬프트 시작',''.join(s.itertext()))
        stored=s.find('TAIL/BINDATASTORAGE/BINDATA')
        self.assertEqual(base64.b64decode(stored.text),server.asset_path(e['id'],c['image']['final_file']).read_bytes())
        self.assertTrue((folder/'정답과해설.hml').exists())
    def test_export_more_than_24(self):
        from tools import gen
        cards=[card(no=n) for n in range(1,26)]
        folder=Path(self.tmp.name)
        hml=gen.build(str(core.TEMPLATE),str(folder/'25.hml'),str(folder),title='25문항',records=server.cards_to_records(cards))
        self.assertIn('25.',hml)
        self.assertEqual(hml.count('<MARKPENBEGIN'),25)
    def test_path_guard(self):
        with self.assertRaises(ValueError):core.exam_path('../templates')
        with self.assertRaises(ValueError):server.asset_path(core.uid(),'../../README.md')
    def test_cli_arguments(self):
        with patch.object(cli,'discover',return_value='codex.exe'):
            args=cli.command('codex',Path(self.tmp.name),{},'')
        self.assertIn('read-only',args);self.assertIn('--output-schema',args)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',args)
    def test_20_questions_exact_total_and_bands(self):
        cards=[card(no=n) for n in range(1,21)]
        for i,c in enumerate(cards): c['difficulty']='하' if i<6 else '중' if i<14 else '상'
        core.allocate_points(cards)
        self.assertAlmostEqual(sum(float(c['points']) for c in cards),100)
        self.assertLess(max(float(c['points']) for c in cards if c['difficulty']=='하'),min(float(c['points']) for c in cards if c['difficulty']=='중'))
        self.assertLess(max(float(c['points']) for c in cards if c['difficulty']=='중'),min(float(c['points']) for c in cards if c['difficulty']=='상'))
        self.assertTrue(all(not c['review_approved'] for c in cards))
        path=Path(self.tmp.name)/'twenty.xlsx';core.export_xlsx(cards,path)
        self.assertEqual(len(core.import_cards(path.read_bytes())),20)
        for c in cards:c['review_approved']=True
        exam=self.exam(cards);bundle=server.export_exam(exam,convert_hwpx=False)
        paper=core.exam_path(exam['id'])/'exports'/bundle['id']/'시험지_교사용.hml'
        root=ET.parse(paper).getroot()
        self.assertEqual(len(list(root.iter('MARKPENBEGIN'))),20)
        self.assertIn('20.',''.join(root.itertext()))
        self.assertNotIn('21.',''.join(root.itertext()))
    def test_card_gate_before_images(self):
        e=self.exam([card()]);e['card_approval']=None;core.save_exam(e)
        with self.assertRaisesRegex(ValueError,'문항카드를 먼저'):
            server.launch_job(e['id'],{'action':'image'})
    def test_card_approval_invalidation(self):
        e=self.exam([card()]);self.assertTrue(core.cards_approved(e))
        e['cards'][0]['question']='달라진 발문';core.save_exam(e)
        self.assertFalse(core.cards_approved(e))
    def test_allocation_counts_and_single_band(self):
        for count in (1,3,20,24,100):
            cards=[card(no=n) for n in range(1,count+1)]
            core.allocate_points(cards)
            self.assertAlmostEqual(sum(float(c['points']) for c in cards),100)

if __name__=='__main__':unittest.main(verbosity=2)
