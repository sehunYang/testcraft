"""앱 그래프 수치 고치기와 다시 그릴 때 글씨 유지(2026-11-13)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
from app import core,images,server,cli,labels
from test_support import cleanup_tempdir
import test_authoring
from test_workflow import card

ROOT=Path(__file__).resolve().parents[1]

def lab(text,x,y,kind='korean',size=20,rotation=0,id=None):
    return dict(id=id or core.uid(),kind=kind,text=text,x=x,y=y,size=size,rotation=rotation)

def chart(values,y_max=30):
    return '도식: '+json.dumps({'type':'chart','chart':'bar','categories':['2000년','2010년','2020년'],'series':[{'name':'A국','values':values}],'y':{'label':'(%)','min':0,'max':y_max,'step':10}},ensure_ascii=False)

class CarryTests(unittest.TestCase):
    def test_moved_label_keeps_its_offset_on_the_new_default(self):
        old=lab('(%)',100,50);moved=dict(old,x=130,y=40)
        new=lab('(%)',120,60)
        kept,defaults=labels.carry([old],[moved],[new])
        self.assertEqual((kept[0]['x'],kept[0]['y']),(150,50))
        self.assertEqual(kept[0]['id'],old['id']);self.assertEqual(defaults[0]['id'],old['id'])
        self.assertEqual((defaults[0]['x'],defaults[0]['y']),(120,60))

    def test_untouched_labels_follow_the_new_spec(self):
        old=lab('2000년',100,500);new=lab('2000년',80,520)
        kept,_=labels.carry([old],[dict(old)],[new])
        self.assertEqual((kept[0]['x'],kept[0]['y']),(80,520))

    def test_edited_text_size_and_hidden_flag_are_kept(self):
        old=lab('A국',300,100);mine=dict(old,text='갑국',size=26,visible=False)
        kept,_=labels.carry([old],[mine],[lab('A국',310,100)])
        self.assertEqual(kept[0]['text'],'갑국');self.assertEqual(kept[0]['size'],26);self.assertIs(kept[0]['visible'],False)

    def test_deleted_label_stays_deleted_and_added_label_stays(self):
        a,b=lab('A',10,10),lab('B',20,20);added=lab('메모',500,300)
        kept,defaults=labels.carry([a,b],[b,added],[lab('A',12,12),lab('B',22,22)])
        self.assertEqual([x['text'] for x in kept],['B','메모'])
        kept2,_=labels.carry(defaults,kept,[lab('A',12,12),lab('B',22,22)])
        self.assertEqual([x['text'] for x in kept2],['B','메모'])

    def test_changed_spec_text_uses_the_new_default(self):
        old=lab('30',50,100,kind='physics');moved=dict(old,x=40)
        kept,_=labels.carry([old],[moved],[lab('40',50,100,kind='physics')])
        self.assertEqual((kept[0]['text'],kept[0]['x']),('40',50))

    def test_offsets_are_clamped_inside_the_canvas(self):
        old=lab('끝',900,600);moved=dict(old,x=990,y=630)
        kept,_=labels.carry([old],[moved],[lab('끝',950,620)])
        self.assertEqual((kept[0]['x'],kept[0]['y']),(1000,640))

class RedrawTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=core.ROOT/'.runtime')
        self.patch=patch.object(core,'DATA',Path(self.tmp.name)/'studio');self.patch.start()
    def tearDown(self):self.patch.stop();cleanup_tempdir(self.tmp)

    def draw(self,e):
        with patch.object(cli,'discover',return_value='fixture'),patch.object(cli,'execute',side_effect=AssertionError('앱 도식은 AI를 부르지 않는다')):
            job=server.launch_job(e['id'],{'action':'image'});test_authoring.AuthoringTests.wait_job(self,job)
        self.assertEqual(job['status'],'completed',job.get('failed'))
        return core.read_exam(e['id'])

    def test_redraw_with_new_values_keeps_the_moved_axis_name(self):
        c=card();c.update(data_kind='image',image_mode='strict',image_locked=chart([12,18,25]),image_creative='',image_text_physics='',image_text_math='',image_text_korean='')
        c['image_plan_approval']={'context':core.image_plan_context(c)}
        e=core.save_exam(dict(id=core.uid(),title='시험',subject='12역학',cards=[c],exports=[],revision=0,card_approval={'digest':core.cards_digest([c])}))
        e=self.draw(e);c=e['cards'][0]
        self.assertEqual(len(c['image']['spec_labels']),len(c['image_labels']))
        unit=next(x for x in c['image_labels'] if x['text']=='(%)');start=(unit['x'],unit['y'])
        unit['x']+=40;unit['y']+=15
        before_ticks={x['text'] for x in c['image_labels']}
        c['image_locked']=chart([12,18,45],y_max=50)                 # 교사가 수치 칸에서 값과 최댓값을 바꿈
        c['image_plan_approval']={'context':core.image_plan_context(c)}
        e['card_approval']={'digest':core.cards_digest([c])};e=core.save_exam(e)
        e=self.draw(e);c=e['cards'][0]
        unit=next(x for x in c['image_labels'] if x['text']=='(%)')
        fresh=next(x for x in c['image']['spec_labels'] if x['text']=='(%)')
        self.assertAlmostEqual(unit['x']-fresh['x'],40,places=2);self.assertAlmostEqual(unit['y']-fresh['y'],15,places=2)
        after_ticks={x['text'] for x in c['image_labels']}
        self.assertIn('50',after_ticks);self.assertNotIn('50',before_ticks)
        self.assertFalse(images.untouched(c))

    def test_legacy_image_without_recorded_defaults_redraws_fresh(self):
        c=card();c.update(data_kind='image',image_mode='strict',image_locked=chart([12,18,25]),image_creative='',image_text_physics='',image_text_math='',image_text_korean='')
        c['image_plan_approval']={'context':core.image_plan_context(c)}
        e=core.save_exam(dict(id=core.uid(),title='시험',subject='12역학',cards=[c],exports=[],revision=0,card_approval={'digest':core.cards_digest([c])}))
        e=self.draw(e);c=e['cards'][0]
        c['image'].pop('spec_labels');c['image_labels'][0]['x']+=30;e=core.save_exam(e)
        e=self.draw(e);c=e['cards'][0]
        self.assertTrue(images.untouched(c))

class PreviewAndPageTests(unittest.TestCase):
    def test_diagram_preview_returns_a_png_or_errors(self):
        try: labels.render('korean','(%)',20)
        except ValueError: self.skipTest('한글 글씨 렌더링 환경(한컴오피스)이 없습니다.')
        ok=images.diagram_preview(chart([12,18,25]))
        self.assertEqual(ok['errors'],[]);self.assertTrue(ok['png'].startswith('data:image/png;base64,'))
        bad=images.diagram_preview(chart([12,18]))
        self.assertTrue(bad['errors']);self.assertNotIn('png',bad)
        self.assertTrue(images.diagram_preview('도식: {')['errors'])

    def test_spec_form_is_loaded_and_served(self):
        page=(ROOT/'app/static/index.html').read_text(encoding='utf-8')
        self.assertIn('<script src="/spec-form.js" defer></script>',page)
        self.assertLess(page.index('/ux-minimal.js'),page.index('/spec-form.js'))
        source=(ROOT/'app/server.py').read_text(encoding='utf-8')
        self.assertIn("'/spec-form.js'",source);self.assertIn("'/spec-form.css'",source);self.assertIn("'/api/diagram-preview'",source)

if __name__=='__main__':
    unittest.main()
