"""Compound-material API invariants and isolated image-job recovery tests."""
import copy
import io
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.runtime/packages'))
from app import core, server
from test_support import cleanup_tempdir
from test_workflow import card
from PIL import Image


class MaterialsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=core.ROOT / '.runtime')
        self.data_patch = patch.object(core, 'DATA', Path(self.tmp.name) / 'studio')
        self.data_patch.start()

    def tearDown(self):
        self.data_patch.stop()
        cleanup_tempdir(self.tmp)

    def exam(self, cards):
        return core.save_exam({
            'id': core.uid(), 'title': '자료 블록 테스트', 'subject': '12역학',
            'cards': cards, 'exports': [], 'revision': 0,
            'card_approval': {'digest': core.cards_digest(cards)},
        })

    def wait_job(self, exam_id, timeout=15):
        deadline = time.monotonic() + timeout
        while exam_id in server.ACTIVE and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertNotIn(exam_id, server.ACTIVE, '작업이 제한 시간 안에 끝나지 않았습니다.')

    @staticmethod
    def image_block(mid, label):
        return {
            'id': mid, 'kind': 'image', 'label': label, 'content': label + ' 그림',
            'image_mode': 'strict', 'image_locked': '수평선과 물체 한 개',
            'image_creative': '', 'image_text_none': True, 'image_plan_version': 2,
        }

    def test_image_job_partial_failure_then_material_only_retry(self):
        c = card()
        first_id, second_id = core.uid(), core.uid()
        c['materials'] = [self.image_block(first_id, '(가)'), self.image_block(second_id, '(나)')]
        c = core.normalize(c, 1)
        for material_id in (first_id, second_id):
            projection, _ = core.material_projection(c, material_id, require_image=True)
            projection['image_plan_approval'] = {'context': core.image_plan_context(projection), 'mode': 'strict'}
            core.sync_material_projection(c, projection, material_id)
        exam = self.exam([c])
        exam_id, card_id = exam['id'], c['id']
        svg = '<svg viewBox="0 0 1000 640"><g id="geometry"><circle cx="500" cy="320" r="100" fill="none" stroke="black"/></g></svg>'
        calls = []

        def fake_execute(provider, folder, prompt, schema, model, cancel):
            target = Path(folder).name
            calls.append(target)
            if target == f'{card_id}-{second_id}-image' and calls.count(target) == 1:
                raise ValueError('격리 검증용 (나) 실패')
            return {'svg': svg, 'description': '검증용 도형', 'constraints': [], 'review_note': ''}

        with patch.object(server.cli, 'discover', return_value='fixture-cli'), patch.object(server.cli, 'execute', side_effect=fake_execute):
            initial = server.launch_job(exam_id, {'action': 'image', 'card_id': card_id})
            self.wait_job(exam_id)
            self.assertEqual(initial['total'], 2)
            self.assertEqual(initial['status'], 'partial')
            self.assertEqual(initial['succeeded'], 1)
            self.assertEqual(initial['failed'][0]['material_id'], second_id)

            saved = core.read_exam(exam_id)['cards'][0]
            first_image = next(b for b in saved['materials'] if b['id'] == first_id)['image']
            self.assertTrue(first_image)
            first_file = server.asset_path(exam_id, first_image['file'])
            first_bytes = first_file.read_bytes()
            self.assertTrue(first_bytes)

            retry = server.launch_job(exam_id, {
                'action': 'image', 'card_id': card_id, 'material_id': second_id,
            })
            self.wait_job(exam_id)
            self.assertEqual(retry['total'], 1)
            self.assertEqual(retry['item_targets'], [{'card_id': card_id, 'material_id': second_id}])
            self.assertEqual(retry['status'], 'completed')

        self.assertEqual(calls, [f'{card_id}-{first_id}-image', f'{card_id}-{second_id}-image', f'{card_id}-{second_id}-image'])
        saved = core.read_exam(exam_id)['cards'][0]
        current_first = next(b for b in saved['materials'] if b['id'] == first_id)['image']
        self.assertEqual(current_first['file'], first_image['file'])
        self.assertEqual(server.asset_path(exam_id, current_first['file']).read_bytes(), first_bytes)
        self.assertTrue(next(b for b in saved['materials'] if b['id'] == second_id)['image'])

    def test_legacy_image_migration_preserves_server_art_and_rejects_spoofs(self):
        c = card()
        c.update(
            data_kind='image', material='등속 운동 자료', image_mode='strict',
            image_locked='수평선과 물체 한 개', image_creative='',
            image_text_physics='v', image_text_none=False, image_plan_version=2,
            image_labels=[{'id': core.uid(), 'kind': 'physics', 'text': 'v', 'x': 100, 'y': 100, 'size': 28, 'rotation': 0}],
            labels_initialized=True,
        )
        c['image_plan_approval'] = {
            'context': core.image_plan_context(c), 'mode': 'strict', 'confirmed_at': 'before-migration',
        }
        exam = self.exam([c])
        exam_id = exam['id']
        c['image'] = server.make_image(exam_id, c, self.png())
        server.finalize_image(exam_id, c)
        core.save_exam(exam)
        old_image = copy.deepcopy(c['image'])
        old_approval = copy.deepcopy(c['image_plan_approval'])
        old_labels = copy.deepcopy(c['image_labels'])
        self.assertTrue(core.image_plan_confirmed(c))

        # The first migrated material keeps the legacy card ID so the server can
        # match its protected asset and confirmation. A new image block carries
        # client-supplied server fields to verify that they are discarded.
        submitted = copy.deepcopy(c)
        legacy = copy.deepcopy(core.material_blocks(c)[0])
        legacy['image'] = {'file': 'f' * 16 + '.png', 'approved': True, 'sha256': 'client-spoof'}
        legacy['image_plan_approval'] = {'context': 'client-spoof', 'mode': 'strict'}
        extra_id = core.uid()
        extra = self.image_block(extra_id, '(나)')
        extra['image'] = {'file': 'e' * 16 + '.png', 'approved': True}
        extra['image_plan_approval'] = {'context': 'client-spoof'}
        submitted['materials'] = [legacy, {
            'id': core.uid(), 'kind': 'text', 'label': '설명', 'content': '추가 글상자',
        }, extra]

        normalized = core.normalize(submitted, 1)
        server.preserve_material_server_state(normalized, c)
        migrated = next(b for b in normalized['materials'] if b['id'] == c['id'])
        added = next(b for b in normalized['materials'] if b['id'] == extra_id)

        self.assertEqual(migrated['image'], old_image)
        self.assertEqual(migrated['image_plan_approval'], old_approval)
        self.assertEqual(migrated['image_labels'], old_labels)
        self.assertTrue(migrated['image']['approved'])
        self.assertTrue(core.image_plan_confirmed(core.material_projection(normalized, c['id'], require_image=True)[0]))
        self.assertIsNone(added['image'])
        self.assertIsNone(added['image_plan_approval'])
        self.assertEqual(normalized['image'], old_image)
        self.assertEqual(normalized['image_plan_approval'], old_approval)

    def test_project_read_and_replace_are_serialized(self):
        exam = self.exam([card()])
        entered_replace = threading.Event()
        release_replace = threading.Event()
        reader_done = threading.Event()
        snapshot_done = threading.Event()
        failures = []
        real_atomic = core.atomic

        def held_atomic(path, value):
            if path.name == 'project.json':
                entered_replace.set()
                if not release_replace.wait(3):
                    raise TimeoutError('테스트용 replace 대기 시간이 초과되었습니다.')
            return real_atomic(path, value)

        def write_exam():
            try:
                core.save_exam(exam)
            except BaseException as exc:
                failures.append(exc)

        def read_exam():
            try:
                core.read_exam(exam['id'])
            except BaseException as exc:
                failures.append(exc)
            finally:
                reader_done.set()

        def read_snapshot():
            try:
                server.read_project_snapshot(core.exam_path(exam['id']) / 'project.json')
            except BaseException as exc:
                failures.append(exc)
            finally:
                snapshot_done.set()

        with patch.object(core, 'atomic', side_effect=held_atomic):
            writer = threading.Thread(target=write_exam)
            writer.start()
            self.assertTrue(entered_replace.wait(2), 'writer가 project.json replace에 도달하지 못했습니다.')
            reader = threading.Thread(target=read_exam)
            snapshot_reader = threading.Thread(target=read_snapshot)
            reader.start()
            snapshot_reader.start()
            try:
                self.assertFalse(reader_done.wait(.05), 'read_exam이 replace 도중 잠금 없이 읽었습니다.')
                self.assertFalse(snapshot_done.wait(.05), 'bootstrap snapshot이 replace 도중 잠금 없이 읽었습니다.')
            finally:
                release_replace.set()
                writer.join(3)
                reader.join(3)
                snapshot_reader.join(3)

        self.assertFalse(writer.is_alive())
        self.assertFalse(reader.is_alive())
        self.assertFalse(snapshot_reader.is_alive())
        self.assertEqual(failures, [])
        self.assertTrue(reader_done.is_set())
        self.assertTrue(snapshot_done.is_set())
        self.assertEqual(core.read_exam(exam['id'])['revision'], exam['revision'])

    @staticmethod
    def png():
        out = io.BytesIO()
        Image.new('RGB', (120, 80), 'white').save(out, format='PNG')
        return out.getvalue()


if __name__ == '__main__':
    unittest.main(verbosity=2)
