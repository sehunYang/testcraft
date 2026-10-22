"""Inline math and explicit approval overrides, using isolated exam storage."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '.runtime/packages'))
from app import core, server
from app.mathtext import math_segments
from test_support import cleanup_tempdir
from test_workflow import card
from tools import gen
from PIL import Image


class InlineMathTests(unittest.TestCase):
    def test_bare_scripted_variables_and_explicit_latex_are_math(self):
        spans = math_segments(r'속도 V_0와 v_y, 명시식 $\frac{1}{2}at^2$')
        self.assertEqual([value for kind, value in spans if kind == 'math'],
                         ['V_0', 'v_y', r'\frac{1}{2}at^2'])

    def test_parenthesized_and_display_latex_delimiters_are_math(self):
        spans = math_segments(r'속도 \(V_0\), 가속도는 \[a=\frac{\Delta v}{t}\]')
        self.assertEqual([value for kind, value in spans if kind == 'math'],
                         ['V_0', r'a=\frac{\Delta v}{t}'])

    def test_double_dollar_delimiter_is_consumed_as_one_math_span(self):
        self.assertEqual(math_segments('초기 속도 $$v_y$$'), [('text','초기 속도 '),('math','v_y')])

    def test_identifier_urls_and_paths_stay_plain_text(self):
        source = r'card_id_v_0 V_0.png https://example.test/a?v_2=1 C:\data\speed_v_3 ./folder/path_v_4'
        self.assertEqual(math_segments(source), [('text', source)])

    def test_hml_runs_emit_equation_elements_for_bare_variables(self):
        runs = gen.runs('속도 V_0와 v_y를 비교한다.')
        equations = [run.find('EQUATION') for run in runs]
        equations = [node for node in equations if node is not None]
        self.assertEqual([node.findtext('SCRIPT') for node in equations],
                         ['{ V _ { 0 } }', '{ v _ { y } }'])
        self.assertEqual(len(equations), 2)


class ApprovalOverrideApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=core.ROOT / '.runtime')
        self.data_patch = patch.object(core, 'DATA', Path(self.tmp.name) / 'studio')
        self.data_patch.start()
        self.exam = None

    def tearDown(self):
        self.data_patch.stop()
        cleanup_tempdir(self.tmp)

    def make_exam(self, item):
        exam = {'id': core.uid(), 'title': '독립 승인 검증', 'subject': '12역학',
                'cards': [item], 'exports': [], 'revision': 0,
                'card_approval': {'digest': core.cards_digest([item])}}
        self.exam = core.save_exam(exam)
        return self.exam

    def test_legacy_card_approval_digest_remains_valid_without_overrides(self):
        item = card()
        exam = self.make_exam(item)
        legacy_digest = hashlib.sha256(json.dumps([
            (item['no'], core.content_hash(item), bool(item['review_approved']))
        ]).encode()).hexdigest()
        exam['card_approval'] = {'digest':legacy_digest, 'approved_at':'legacy'}
        self.exam = core.save_exam(exam)
        self.assertEqual(core.cards_digest([item]), legacy_digest)
        self.assertTrue(core.cards_approved(self.exam))

    def test_legacy_export_digest_payload_is_unchanged_without_overrides(self):
        item = card()
        item['data_kind'] = 'image'
        item['image'] = {'final_sha256':'f'*64, 'final_digest':'e'*64, 'sha256':'d'*64}
        exam = {'title':'기존 출력', 'subject':'12역학', 'cards':[item]}
        fields = {key:item.get(key,'') for key in core.COLS.values() if key!='no'}
        fields['no'] = item['no']
        fields['data_kind'] = item['data_kind']
        image = item['image']
        fields['final_image'] = {'final_sha256':image.get('final_sha256'),
                                 'current_digest':core.image_final_digest(item),
                                 'final_digest':image.get('final_digest'),
                                 'source_sha256':image.get('sha256')}
        legacy = hashlib.sha256(json.dumps({'title':exam['title'],'subject':exam['subject'],'cards':[fields]},
                                           sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(core.export_digest(exam), legacy)

    def post(self, path, payload):
        body = dict(payload, exam_id=self.exam['id'], revision=self.exam['revision'])
        encoded = json.dumps(body).encode()

        class MemoryHandler(server.Handler):
            def __init__(self):
                self.path = path
                self.headers = {'Host':'127.0.0.1','X-Studio-Token':server.TOKEN,
                                'Content-Length':str(len(encoded))}
                self.rfile = io.BytesIO(encoded)
                self.wfile = io.BytesIO()
                self.status = None

            def send_response(self, status, message=None): self.status = status
            def send_header(self, key, value): pass
            def end_headers(self): pass

        handler = MemoryHandler()
        handler.do_POST()
        return handler.status, json.loads(handler.wfile.getvalue().decode())

    @staticmethod
    def png():
        stream = io.BytesIO()
        Image.new('RGB', (120, 80), 'white').save(stream, format='PNG')
        return stream.getvalue()

    def test_failed_calculation_requires_a_digest_bound_explicit_override(self):
        item = card()
        item.update(review_approved=False, checks=[{'label': '속력', 'lhs': '2*2', 'rhs': '5'}])
        self.make_exam(item)

        status, result = self.post('/api/approve', {'card_id': item['id'], 'kind': 'question', 'approved': True})
        self.assertEqual(status, 409)
        self.assertEqual(result['code'], 'approval_discrepancy')
        details = result['details']
        self.assertTrue(details['override_allowed'])
        self.assertFalse(details['checks'][0]['ok'])

        status, malformed_result = self.post('/api/approve', {'card_id':item['id'], 'kind':'question', 'approved':True,
                                                               'override':['calculation', details['validation_digest']]})
        self.assertEqual(status, 409)
        self.assertTrue(malformed_result['details']['override_rejected'])

        status, override_result = self.post('/api/approve', {'card_id': item['id'], 'kind': 'question', 'approved': True,
                                                            'override': {'kind': 'calculation', 'validation_digest': details['validation_digest']}})
        if status != 200: raise AssertionError(override_result)
        saved = core.read_exam(self.exam['id'])
        self.exam = saved
        self.assertTrue(saved['cards'][0]['review_approved'])
        self.assertTrue(core.calculation_override_active(saved['cards'][0]))
        self.assertTrue(core.validate(saved, 'cards')['ready'])
        self.assertFalse(core.cards_approved(saved))
        saved['card_approval'] = {'digest':core.cards_digest(saved['cards'])}
        self.exam = core.save_exam(saved)
        saved = core.read_exam(self.exam['id'])
        self.assertTrue(core.validate(saved)['ready'])
        self.assertIn('시험지_학생용.hml', server.export_exam(saved)['files'])

        changed = copy.deepcopy(saved['cards'][0])
        changed['checks'][0]['rhs'] = '4'
        status, _ = self.post('/api/save', {'title': saved['title'], 'subject': saved['subject'], 'cards': [changed]})
        self.assertEqual(status, 200)
        saved = core.read_exam(self.exam['id'])
        self.assertIsNone(saved['cards'][0]['calculation_override'])
        self.assertFalse(saved['cards'][0]['review_approved'])

    def test_missing_calculation_input_is_a_non_overridable_gate(self):
        item = card()
        item.update(review_approved=False, checks=[])
        self.make_exam(item)
        status, result = self.post('/api/approve', {'card_id': item['id'], 'kind': 'question', 'approved': True,
                                                    'override': {'kind': 'calculation', 'validation_digest': 'anything'}})
        self.assertEqual(status, 400)
        self.assertEqual(result['code'], 'approval_blocked')
        self.assertFalse(result['details']['override_allowed'])
        status, _ = self.post('/api/approve', {'card_id':item['id'], 'kind':'question', 'approved':False})
        self.assertEqual(status, 200)

    def test_cancelling_image_approval_is_allowed_when_card_approval_is_stale(self):
        item = card()
        item.update(review_approved=True, data_kind='image', material='수평면의 물체', image_mode='strict',
                    image_locked='floor: 수평선', image_creative='', image_text_none=True, labels_initialized=True)
        item['image_plan_approval'] = {'context': core.image_plan_context(item), 'mode': 'strict'}
        exam = self.make_exam(item)
        item['image'] = server.make_image(exam['id'], item, self.png(),
                                          checks=[{'label':'길이 비례','ok':False,'detail':'-1'}])
        item['image']['approved'] = True
        item['image']['approval_override'] = {'stale':'test record'}
        exam['cards'] = [item]
        exam['card_approval'] = None
        self.exam = core.save_exam(exam)

        status, _ = self.post('/api/approve', {'card_id':item['id'], 'kind':'image', 'approved':False})
        self.assertEqual(status, 200)
        saved = core.read_exam(self.exam['id'])
        self.assertFalse(saved['cards'][0]['image']['approved'])
        self.assertNotIn('approval_override', saved['cards'][0]['image'])

    def test_failed_image_check_can_be_overridden_but_content_edit_reopens_it(self):
        item = card()
        item.update(review_approved=True, data_kind='image', material='수평면의 물체', image_mode='strict',
                    image_locked='floor: 수평선', image_creative='', image_text_none=True, labels_initialized=True)
        item['image_plan_approval'] = {'context': core.image_plan_context(item), 'mode': 'strict'}
        exam = self.make_exam(item)
        item['image'] = server.make_image(exam['id'], item, self.png(),
                                          checks=[{'label':'길이 비례','ok':False,'detail':'-1'},
                                                  {'label':'힘 평형','ok':True,'detail':'0'}])
        exam['cards'] = [item]
        self.exam = core.save_exam(exam)

        status, result = self.post('/api/approve', {'card_id': item['id'], 'kind': 'image', 'approved': True})
        self.assertEqual(status, 409)
        self.assertEqual(result['details']['kind'], 'image')
        self.assertEqual(result['details']['checks'], [{'label':'길이 비례','ok':False,'detail':'-1'},
                                                       {'label':'힘 평형','ok':True,'detail':'0'}])
        token = result['details']['validation_digest']
        status, result = self.post('/api/approve', {'card_id': item['id'], 'kind': 'image', 'approved': True,
                                                    'override': {'kind': 'image', 'validation_digest': token}})
        if status != 200: raise AssertionError(result)
        saved = core.read_exam(self.exam['id'])
        self.exam = saved
        self.assertTrue(core.image_override_active(saved['cards'][0]))
        self.assertEqual(saved['cards'][0]['image']['checks'], [{'label':'길이 비례','ok':False,'detail':'-1'},
                                                                {'label':'힘 평형','ok':True,'detail':'0'}])
        self.assertTrue(core.validate(saved)['ready'])
        self.assertIn('시험지_학생용.hml', server.export_exam(saved)['files'])

        changed = copy.deepcopy(saved['cards'][0])
        changed['question'] += ' 조건을 추가한다.'
        status, _ = self.post('/api/save', {'title': saved['title'], 'subject': saved['subject'], 'cards': [changed]})
        self.assertEqual(status, 200)
        saved = core.read_exam(self.exam['id'])
        self.assertFalse(saved['cards'][0]['image']['approved'])
        self.assertNotIn('approval_override', saved['cards'][0]['image'])
        self.assertFalse(core.validate(saved)['ready'])

    def test_successful_image_check_keeps_the_actual_result_detail(self):
        item = card()
        item.update(review_approved=True, data_kind='image', material='수평면의 물체', image_mode='strict',
                    image_locked='floor: 수평선', image_creative='', image_text_none=True, labels_initialized=True)
        item['image_plan_approval'] = {'context': core.image_plan_context(item), 'mode': 'strict'}
        exam = self.make_exam(item)
        item['image'] = server.make_image(exam['id'], item, self.png(),
                                          checks=[{'label':'길이 비례','ok':True,'detail':'0'},
                                                  {'label':'힘 평형','ok':True,'detail':'0'}])
        self.assertEqual(item['image']['checks'], [{'label':'길이 비례','ok':True,'detail':'0'},
                                                   {'label':'힘 평형','ok':True,'detail':'0'}])
        exam['cards'] = [item]
        self.exam = core.save_exam(exam)

        status, _ = self.post('/api/approve', {'card_id': item['id'], 'kind': 'image', 'approved': True})
        self.assertEqual(status, 200)
        saved = core.read_exam(self.exam['id'])
        self.exam = saved
        self.assertEqual(saved['cards'][0]['image']['checks'], [{'label':'길이 비례','ok':True,'detail':'0'},
                                                                {'label':'힘 평형','ok':True,'detail':'0'}])
        self.assertNotIn('approval_override', saved['cards'][0]['image'])
        self.assertTrue(core.validate(saved)['ready'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
