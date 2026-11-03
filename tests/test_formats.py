import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.runtime/packages'))
from app import cli, core, formats

MAP_MATCH = {'id': 'geo_map_match', 'name': '지도 위치 대응형', 'subjects': ['12세지'], 'types': ['짝짓기형', '최선답형'],
             'material': '글 (가)~(다)와 지도 A~E', 'question': '(가)~(다) 지역을 지도의 A~E에서 고른 것은?',
             'choices': '순열 짝 다섯 줄', 'app': '앱 지도', 'cautions': '', 'manual': '지리사회.md H1'}


class FormatTests(unittest.TestCase):
    def test_catalog_entries_are_complete_and_use_known_subjects_and_types(self):
        known = set(core.standards()[k]['subject'] for k in core.standards())
        ids = [f['id'] for f in formats.catalog()]
        self.assertEqual(len(ids), len(set(ids)))
        for f in formats.catalog():
            self.assertEqual(formats.normalize(f['id']), f['id'])
            self.assertTrue(f['name'] and f['material'] and f['question'], f['id'])
            self.assertTrue(set(f['types']) <= set(core.TYPES + core.SUBJECTIVE_TYPES), f['id'])
            self.assertTrue(f['subjects'] and set(f['subjects']) <= known, (f['id'], set(f['subjects']) - known))

    def test_card_keeps_the_chosen_format_without_touching_its_approval(self):
        card = core.blank_card(1)
        card.update(type='짝짓기형', idea='지도의 지역 고르기')
        before = core.content_hash(card)
        card['format'] = 'geo_map_match'
        self.assertEqual(core.normalize(card, 1)['format'], 'geo_map_match')
        self.assertEqual(core.content_hash(card), before)        # 입력 메타데이터라 승인이 풀리지 않는다
        with self.assertRaises(ValueError): core.normalize({**card, 'format': '<script>'}, 1)

    def test_question_request_carries_the_format_only_for_its_subject(self):
        card = core.blank_card(1)
        card.update(type='짝짓기형', idea='세 지역의 기후', format='geo_map_match')
        with patch.object(formats, 'catalog', lambda: [MAP_MATCH]):
            prompt = cli.prompt_for(card, 'question', subject_id='12세지')
            self.assertIn('세부 형식: 지도 위치 대응형', prompt)
            self.assertIn('(가)~(다) 지역을 지도의 A~E에서 고른 것은?', prompt)
            self.assertNotIn('세부 형식:', cli.prompt_for(card, 'question', subject_id='12물리'))
            self.assertEqual([f['id'] for f in formats.for_subject('12세지')], ['geo_map_match'])


if __name__ == '__main__':
    unittest.main()
