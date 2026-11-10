import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from app import cli, core, variants


def png_data(w=200, h=100):
    out = io.BytesIO()
    Image.new('RGB', (w, h), 'white').save(out, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()


class VariantTests(unittest.TestCase):
    def card(self, **variant):
        card = core.blank_card(1, 'variant')
        card.update(type='최선답형', difficulty='중')
        card['variant'] = {'methods': ['numbers'], 'memo': '', 'source': {'kind': 'kice', 'key': '2025-수능-물리학Ⅰ-20', 'label': '2025학년도 대학수학능력시험 물리학Ⅰ 20번', 'image': 'a' * 16 + '.png'}, **variant}
        variants.normalize(card)
        return card

    def test_mode_is_allowed(self):
        self.assertEqual(core.normalize_authoring_mode('variant'), 'variant')

    def test_normalize_keeps_only_known_methods_and_safe_source(self):
        card = self.card(methods=['form', 'bogus', 'numbers'])
        self.assertEqual(card['variant']['methods'], ['numbers', 'form'])
        card['variant']['source']['image'] = '../escape.png'
        variants.normalize(card)
        self.assertIsNone(card['variant']['source'])

    def test_check_requires_source_and_method(self):
        with self.assertRaisesRegex(ValueError, '변형 방식'):
            variants.check(self.card(methods=[]))
        card = self.card(); card['variant']['source'] = None
        with self.assertRaisesRegex(ValueError, '원본'):
            variants.check(card)

    def test_prompt_contains_only_chosen_methods(self):
        text = variants.prompt(self.card(methods=['numbers']))
        self.assertIn('수치·조건만 바꾸기', text)
        self.assertNotIn('상황 바꾸고 원리 유지', text)
        self.assertIn('유형·난이도는 바꾸지 않는다', text)
        self.assertIn('상황·소재는 원본과 같은 종류', text)
        text = variants.prompt(self.card(methods=['situation', 'form'], memo='표로 바꿔 주세요'))
        self.assertIn('목표 유형은 \'최선답형\'', text)
        self.assertNotIn('유형·난이도는 바꾸지 않는다', text)
        self.assertIn('표로 바꿔 주세요', text)

    def test_question_prompt_includes_variant_instruction(self):
        prompt = cli.prompt_for(self.card(), 'question', subject='물리학', subject_id='12물리')
        self.assertIn('원본 기출 문항 그림을 바탕으로 한 변형 문항', prompt)
        self.assertIn('variant_changes', prompt)

    def test_variant_schema_adds_changes(self):
        variant = cli.schema_for('question', True)
        self.assertIn('variant_changes', variant['properties'])
        self.assertEqual(set(variant['properties']) - {'variant_changes'}, set(cli.schema_for('question')['properties']))
        self.assertEqual(set(variant['required']), set(variant['properties']))
        self.assertNotIn('variant_changes', cli.schema_for('question')['properties'])

    def test_codex_command_puts_images_before_other_flags(self):
        with mock.patch.object(cli, 'discover', return_value='C:/x/codex.exe'):
            args = cli.command('codex', Path('job'), {}, '', (Path('src.png'),))
        self.assertEqual(args[2:4], ['--image', 'src.png'])
        self.assertEqual(args[-1], '-')
        with mock.patch.object(cli, 'discover', return_value='C:/x/claude.exe'):
            with self.assertRaisesRegex(ValueError, 'Codex'):
                cli.command('claude', Path('job'), {}, '', (Path('src.png'),))

    def test_upload_is_cropped_and_saved_in_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = variants.save_source(tmp, {'kind': 'upload', 'name': '내 문제.png', 'data': png_data(), 'crop': [0, 0, .5, .5], 'label': '2024 중간고사 3번'}, 'b' * 16)
            self.assertEqual(source['label'], '2024 중간고사 3번')
            with Image.open(Path(tmp) / 'sources' / source['image']) as saved:
                self.assertEqual(saved.size, (100, 50))
            self.assertIsNotNone(variants.source_file(tmp, source))
            with self.assertRaisesRegex(ValueError, '너무 작습니다'):
                variants.save_source(tmp, {'kind': 'upload', 'name': 'a.png', 'data': png_data(), 'crop': [0, 0, .01, .5]}, 'c' * 16)

    def test_pdf_crop_keeps_only_text_inside_the_box(self):
        import pymupdf
        doc = pymupdf.open()
        sheet = doc.new_page(width=400, height=400)
        sheet.insert_text((20, 50), 'TOP QUESTION TEXT')
        sheet.insert_text((20, 350), 'BOTTOM OTHER TEXT')
        data = 'data:application/pdf;base64,' + base64.b64encode(doc.tobytes()).decode()
        doc.close()
        with tempfile.TemporaryDirectory() as tmp:
            source = variants.save_source(tmp, {'kind': 'upload', 'name': 'p.pdf', 'data': data, 'crop': [0, 0, 1, .5]}, 'd' * 16)
            text = variants.source_file(tmp, source, '.txt').read_text(encoding='utf-8')
            self.assertIn('TOP QUESTION', text)
            self.assertNotIn('BOTTOM', text)
            with self.assertRaisesRegex(ValueError, '1~1'):
                variants.save_source(tmp, {'kind': 'upload', 'name': 'p.pdf', 'data': data, 'page': 3}, 'e' * 16)

    def test_overlap_flags_copied_text(self):
        original = '그림과 같이 높이 4h인 평면에서 용수철 P에 연결된 물체 A에 물체 B를 접촉시켜'
        copied = {'stem': original, 'question': ''}
        fresh = {'stem': '수평면 위의 수레가 언덕을 오른 뒤 정지한다. 마찰 구간의 길이를 구하시오.', 'question': ''}
        self.assertGreater(variants.overlap(original, copied), .9)
        self.assertLess(variants.overlap(original, fresh), .1)
        self.assertEqual(variants.overlap('', copied), 0.0)

    def test_overlap_limit_is_looser_for_numbers_only(self):
        self.assertEqual(variants.overlap_limit(self.card(methods=['numbers'])), .5)
        self.assertEqual(variants.overlap_limit(self.card(methods=['numbers', 'situation'])), .25)
        self.assertEqual(variants.overlap_limit(self.card(methods=['form'])), .25)

    def test_answer_note_only_for_variant_cards(self):
        card = self.card()
        self.assertEqual(variants.answer_note(card), '[출처] 2025학년도 대학수학능력시험 물리학Ⅰ 20번 변형')
        card['authoring_mode'] = 'ai'
        self.assertEqual(variants.answer_note(card), '')

    def test_variant_metadata_does_not_withdraw_approval(self):
        card = self.card()
        before = core.content_hash(card)
        card['variant']['changes'] = ['질량 2 kg → 3 kg']
        self.assertEqual(core.content_hash(card), before)


if __name__ == '__main__':
    unittest.main()
