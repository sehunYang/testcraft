"""Server-side card duplication, isolated from production exam storage."""
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '.runtime/packages'))
from app import core, server, vectors
from test_support import cleanup_tempdir
from test_workflow import card


SVG = '<svg viewBox="0 0 1000 640"><g id="geometry"><circle cx="500" cy="320" r="80" fill="none" stroke="black"/></g></svg>'


class CardDuplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.runtime')
        self.data_patch = patch.object(core, 'DATA', Path(self.tmp.name) / 'studio')
        self.data_patch.start()
        self.active_before = dict(server.ACTIVE)

    def tearDown(self):
        server.ACTIVE.clear()
        server.ACTIVE.update(self.active_before)
        self.data_patch.stop()
        cleanup_tempdir(self.tmp)

    def save_exam(self, cards, eid=None):
        return core.save_exam({
            'id': eid or core.uid(), 'title': '복제 검증', 'subject': '12역학',
            'cards': cards, 'exports': [], 'revision': 0,
            'card_approval': {'digest': core.cards_digest(cards)},
        })

    @staticmethod
    def image_record(eid, *, write=True):
        directory = core.exam_path(eid) / 'assets'
        directory.mkdir(parents=True, exist_ok=True)
        names = {
            'file': core.uid() + '.png',
            'svg': core.uid() + '.svg',
            'edited_file': core.uid() + '.png',
            'edited_svg': core.uid() + '.svg',
            'final_file': core.uid() + '.png',
        }
        payloads = {
            'file': b'raw image bytes',
            'svg': SVG.encode(),
            'edited_file': b'edited image bytes',
            'edited_svg': SVG.replace('r="80"', 'r="90"').encode(),
            'final_file': b'final approved image bytes',
        }
        if write:
            for field, name in names.items():
                (directory / name).write_bytes(payloads[field])
        scene = vectors.from_svg(SVG, hashlib.sha256(payloads['file']).hexdigest())
        scene['objects'][0]['matrix'] = [1, 0, 0, 1, 18, 27]
        return ({
            **names,
            'sha256': hashlib.sha256(payloads['file']).hexdigest(),
            'edited_sha256': hashlib.sha256(payloads['edited_file']).hexdigest(),
            'edited_digest': 'editable-scene-digest',
            'final_sha256': hashlib.sha256(payloads['final_file']).hexdigest(),
            'final_digest': 'approved-artifact-digest',
            'approved': True,
            'approval_override': {'approved_at': 'source approval'},
            'checks': [{'label': '비례', 'ok': True, 'detail': '일치'}],
            'note': '생성 기록 보존',
            'mode': 'strict',
            'layer_version': 2,
        }, scene, payloads)

    def post(self, path, payload):
        body = dict(payload, exam_id=self.exam['id'])
        encoded = json.dumps(body).encode()

        class MemoryHandler(server.Handler):
            def __init__(self):
                self.path = path
                self.headers = {'Host': '127.0.0.1', 'X-Studio-Token': server.TOKEN,
                                'Content-Length': str(len(encoded))}
                self.rfile = io.BytesIO(encoded)
                self.wfile = io.BytesIO()
                self.status = None

            def send_response(self, status, message=None): self.status = status
            def send_header(self, key, value): pass
            def end_headers(self): pass

        handler = MemoryHandler()
        handler.do_POST()
        return handler.status, json.loads(handler.wfile.getvalue().decode())

    def duplicate(self, source, *, revision=None, request_id='attempt-1'):
        return self.post('/api/duplicate-card', {
            'revision': self.exam['revision'] if revision is None else revision,
            'card_id': source, 'request_id': request_id,
        })

    def test_legacy_duplicate_inserts_after_source_and_resets_only_clone_workflow(self):
        source = card(no=1)
        source.update(
            authoring_mode='ai', ai_requested=True, ai_feedback='유지할 요청',
            materials_request='속도 화살표 그림', material_request_kinds=['image'],
            material_request_image_mode='strict', image_plan_approval={'context': 'source plan'},
            calculation_override={'content_digest': 'source override'},
        )
        later = card(no=2)
        later['points'] = '7'
        self.exam = self.save_exam([source, later])
        before = core.read_exam(self.exam['id'])
        self.assertTrue(core.cards_approved(before))

        status, result = self.duplicate(source['id'])

        self.assertEqual(status, 200, result)
        saved = core.read_exam(self.exam['id'])
        self.assertEqual([item['id'] for item in saved['cards']], [source['id'], result['card_id'], later['id']])
        self.assertEqual([item['no'] for item in saved['cards']], [1, 2, 3])
        clone = saved['cards'][1]
        self.assertNotEqual(clone['id'], source['id'])
        self.assertEqual(clone['points'], '')
        self.assertFalse(clone['review_approved'])
        self.assertFalse(clone['ai_requested'])
        self.assertIsNone(clone['calculation_override'])
        self.assertIsNone(clone['image_plan_approval'])
        for field in ('idea', 'stem', 'question', 'choices', 'answer', 'explanation', 'checks',
                      'materials_request', 'material_request_kinds', 'material_request_image_mode',
                      'authoring_mode', 'ai_feedback'):
            self.assertEqual(clone[field], before['cards'][0][field], field)
        self.assertEqual(saved['cards'][0], before['cards'][0])
        self.assertEqual(saved['cards'][2]['points'], '7')
        self.assertFalse(core.cards_approved(saved))
        self.assertFalse(result['exam']['cards_approved'])

    def test_compound_duplicate_has_fresh_material_and_image_assets_and_keeps_editable_state(self):
        source = card(no=1)
        eid = core.uid()
        image, scene, payloads = self.image_record(eid)
        image_id, text_id, table_id = core.uid(), core.uid(), core.uid()
        label = {'id': core.uid(), 'kind': 'physics', 'text': 'v_0', 'size': 28,
                 'x': 420, 'y': 260, 'rotation': 0}
        source['materials'] = [
            {'id': image_id, 'kind': 'image', 'label': '(가)', 'content': '속도 화살표',
             'image_mode': 'strict', 'image_locked': '수평선과 화살표', 'image_creative': '',
             'image_text_none': False, 'image_text_physics': 'v_0', 'image_text_math': '',
             'image_text_korean': '', 'image_plan_version': 2,
             'image_plan_approval': {'context': 'source plan'}, 'image_labels': [label],
             'labels_initialized': True, 'image_scene': scene, 'image': image},
            {'id': text_id, 'kind': 'text', 'label': '(나)', 'content': '(글상자)\n속력이 $v_0$이다.'},
            {'id': table_id, 'kind': 'table', 'label': '(다)', 'content': '| 시간 | 속력 |\n|---|---|\n| 1 s | 2 m/s |'},
        ]
        source['calculation_override'] = {'content_digest': 'source override'}
        source = core.normalize(source, 1)
        self.exam = self.save_exam([source], eid)
        before = core.read_exam(self.exam['id'])['cards'][0]
        source_image = next(block for block in before['materials'] if block['kind'] == 'image')['image']

        status, result = self.duplicate(source['id'])

        self.assertEqual(status, 200, result)
        saved = core.read_exam(self.exam['id'])
        original, clone = saved['cards']
        self.assertEqual(original, before)
        self.assertIsNone(clone['calculation_override'])
        self.assertEqual(clone['points'], '')
        self.assertFalse(clone['review_approved'])
        self.assertEqual(len(clone['materials']), 3)
        original_blocks = {block['label']: block for block in original['materials']}
        clone_blocks = {block['label']: block for block in clone['materials']}
        self.assertEqual({label: block['kind'] for label, block in clone_blocks.items()},
                         {'(가)': 'image', '(나)': 'text', '(다)': 'table'})
        for block in clone['materials']:
            self.assertNotEqual(block['id'], original_blocks[block['label']]['id'])
        self.assertEqual(clone_blocks['(나)']['content'], original_blocks['(나)']['content'])
        self.assertEqual(clone_blocks['(다)']['content'], original_blocks['(다)']['content'])
        cloned_image_block = clone_blocks['(가)']
        cloned_image = cloned_image_block['image']
        self.assertFalse(cloned_image['approved'])
        self.assertNotIn('approval_override', cloned_image)
        self.assertNotIn('final_file', cloned_image)
        self.assertNotIn('final_sha256', cloned_image)
        self.assertNotIn('final_digest', cloned_image)
        self.assertIsNone(cloned_image_block['image_plan_approval'])
        self.assertEqual(cloned_image_block['image_labels'], [label])
        self.assertEqual(cloned_image_block['image_scene'], scene)
        self.assertEqual(clone['image_labels'], [label])
        self.assertEqual(clone['image_scene'], scene)
        for field in ('file', 'svg', 'edited_file', 'edited_svg'):
            self.assertNotEqual(cloned_image[field], source_image[field])
            source_bytes = server.asset_path(self.exam['id'], source_image[field]).read_bytes()
            clone_bytes = server.asset_path(self.exam['id'], cloned_image[field]).read_bytes()
            self.assertEqual(clone_bytes, payloads[field])
            self.assertEqual(source_bytes, clone_bytes)
        self.assertTrue(server.asset_path(self.exam['id'], source_image['final_file']).exists())
        self.assertEqual(original['image']['file'], source_image['file'])
        self.assertEqual(result['exam']['cards'][1]['materials'][0]['image']['file'], cloned_image['file'])

    def test_missing_source_image_asset_fails_without_adding_card(self):
        source = card(no=1)
        source['data_kind'] = 'image'
        source['image'] = {'file': core.uid() + '.png', 'sha256': 'a' * 64, 'approved': True}
        self.exam = self.save_exam([source])
        before = core.read_exam(self.exam['id'])

        status, result = self.duplicate(source['id'])

        self.assertEqual(status, 400)
        self.assertIn('그림 파일을 찾을 수 없습니다', result['error'])
        self.assertEqual(core.read_exam(self.exam['id'])['cards'], before['cards'])
        self.assertEqual(list((core.exam_path(self.exam['id']) / 'assets').glob('*')) if (core.exam_path(self.exam['id']) / 'assets').exists() else [], [])

    def test_card_limit_and_revision_and_active_gates(self):
        cards = [card(no=index) for index in range(1, 101)]
        self.exam = self.save_exam(cards)
        status, result = self.duplicate(cards[49]['id'])
        self.assertEqual(status, 400)
        self.assertIn('1~100개', result['error'])
        self.assertEqual(len(core.read_exam(self.exam['id'])['cards']), 100)

        stale_status, stale_result = self.duplicate(cards[0]['id'], revision=self.exam['revision'] - 1,
                                                     request_id='stale-attempt')
        self.assertEqual(stale_status, 409)
        self.assertEqual(stale_result['code'], 'revision_conflict')

        server.ACTIVE[self.exam['id']] = 'job-in-progress'
        active_status, active_result = self.duplicate(cards[0]['id'], request_id='active-attempt')
        self.assertEqual(active_status, 400)
        self.assertIn('생성 작업 중', active_result['error'])

    def test_request_id_retry_reuses_clone_even_with_stale_revision(self):
        source, later = card(no=1), card(no=2)
        self.exam = self.save_exam([source, later])
        original_revision = self.exam['revision']

        first_status, first = self.duplicate(source['id'], request_id='stable-attempt')
        self.assertEqual(first_status, 200, first)
        saved_revision = first['exam']['revision']
        retry_status, retry = self.duplicate(source['id'], revision=original_revision,
                                              request_id='stable-attempt')
        self.assertEqual(retry_status, 200, retry)
        self.assertEqual(retry['card_id'], first['card_id'])
        self.assertEqual(retry['exam']['revision'], saved_revision)
        self.assertEqual(len(core.read_exam(self.exam['id'])['cards']), 3)

        wrong_source_status, wrong_source = self.duplicate(later['id'], revision=original_revision,
                                                            request_id='stable-attempt')
        self.assertEqual(wrong_source_status, 400)
        self.assertIn('다른 문항 복제', wrong_source['error'])

    def test_request_id_does_not_recreate_a_clone_deleted_after_first_success(self):
        source = card(no=1)
        self.exam = self.save_exam([source])
        first_status, first = self.duplicate(source['id'], request_id='deleted-clone-attempt')
        self.assertEqual(first_status, 200, first)
        saved = core.read_exam(self.exam['id'])
        saved['cards'] = [item for item in saved['cards'] if item['id'] != first['card_id']]
        self.exam = core.save_exam(saved)

        retry_status, retry = self.duplicate(source['id'], request_id='deleted-clone-attempt')

        self.assertEqual(retry_status, 400)
        self.assertIn('삭제되었습니다', retry['error'])
        self.assertEqual([item['id'] for item in core.read_exam(self.exam['id'])['cards']], [source['id']])

    def test_duplicate_save_failure_rolls_back_new_assets_and_card(self):
        source = card(no=1)
        eid = core.uid()
        image, scene, _ = self.image_record(eid)
        source.update(data_kind='image', image=image, image_scene=scene)
        self.exam = self.save_exam([source], eid)
        before = core.read_exam(self.exam['id'])
        asset_dir = core.exam_path(self.exam['id']) / 'assets'
        existing_files = {path.name for path in asset_dir.iterdir()}

        with patch.object(core, 'save_exam', side_effect=OSError('isolated write failure')):
            status, result = self.duplicate(source['id'])

        self.assertEqual(status, 400)
        self.assertIn('isolated write failure', result['error'])
        self.assertEqual(core.read_exam(self.exam['id'])['cards'], before['cards'])
        self.assertEqual({path.name for path in asset_dir.iterdir()}, existing_files)


if __name__ == '__main__':
    unittest.main()
