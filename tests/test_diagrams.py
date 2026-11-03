import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.runtime/packages'))
from app import cli, core, diagrams, images


def spec(**fields):
    return diagrams.PREFIX + ' ' + json.dumps(fields, ensure_ascii=False)


EXAMPLES = {
    'pedigree': dict(generations=[['1', '2'], ['3', '4']], people=[{'id': '1', 'sex': 'M', 'trait': 'a'}, {'id': '2', 'sex': 'F'},
                     {'id': '3', 'sex': 'F', 'trait': 'ab'}, {'id': '4', 'sex': 'M', 'carrier': True}], couples=[['1', '2']],
                     children=[{'parents': ['1', '2'], 'kids': ['3', '4']}]),
    'foodweb': dict(levels=[['풀'], ['메뚜기', '토끼'], ['뱀']], links=[['풀', '메뚜기'], ['풀', '토끼'], ['메뚜기', '뱀'], ['토끼', '뱀']]),
    'pyramid': dict(levels=[{'label': '생산자', 'value': 100}, {'label': '1차 소비자', 'value': 10}]),
    'sequence': dict(strands=[{'label': 'DNA', 'seq': 'TAC', 'ends': ['3′', '5′']}, {'label': 'mRNA', 'seq': 'AUG', 'codons': True, 'marks': [{'from': 0, 'to': 2, 'label': '㉠'}]}], pairs=[[0, 1]]),
    'cell': dict(kind='plant', marks=[{'organelle': 'chloroplast', 'label': 'A'}, {'organelle': 'vacuole', 'label': 'B'}]),
    'particles': dict(panels=[{'label': '반응 전', 'molecules': [{'atoms': ['H', 'H'], 'count': 2}, {'atoms': ['O', 'O'], 'count': 1}]},
                              {'label': '반응 후', 'molecules': [{'atoms': ['O', 'H', 'H'], 'count': 2}]}]),
    'energy': dict(reactant=0, product=-30, peak=50, catalyst=20, marks=[{'from': 'reactant', 'to': 'peak', 'label': '(가)'}]),
}


class DiagramTests(unittest.TestCase):
    def test_every_type_draws_a_strict_figure_with_text_in_the_label_layer(self):
        for kind, fields in EXAMPLES.items():
            with self.subTest(kind):
                svg, labels = diagrams.render(spec(type=kind, **fields))
                images.validate_mode_layers(svg, 'strict')
                self.assertNotIn('<text', svg)
                self.assertTrue(labels)

    def test_pedigree_numbers_each_person_and_builds_a_legend(self):
        _, labels = diagrams.render(spec(type='pedigree', **EXAMPLES['pedigree']))
        texts = [x['text'] for x in labels]
        self.assertTrue({'1', '2', '3', '4'} <= set(texts))
        self.assertIn('정상 남자', texts)
        self.assertTrue(any('발현' in t for t in texts))

    def test_mistakes_are_named_for_the_teacher(self):
        self.assertTrue(any('type' in e for e in diagrams.errors(spec(type='tree'))))
        self.assertTrue(any('구성원 9' in e for e in diagrams.errors(spec(type='pedigree', generations=[['9']], people=[]))))
        self.assertTrue(any('같아야' in e for e in diagrams.errors(spec(type='sequence', strands=[{'seq': 'TA'}, {'seq': 'AUG'}], pairs=[[0, 1]]))))
        self.assertTrue(any('동물 세포' in e for e in diagrams.errors(spec(type='cell', kind='animal', marks=[{'organelle': 'chloroplast', 'label': 'A'}]))))
        self.assertTrue(any('peak' in e for e in diagrams.errors(spec(type='energy', reactant=0, product=10, peak=5))))

    def test_plan_check_accepts_a_diagram_and_science_prompts_explain_it(self):
        card = core.blank_card(1); card.update(data_kind='image', image_mode='strict', image_locked=spec(type='energy', **EXAMPLES['energy']))
        self.assertEqual(core.image_plan_errors(card), [])
        card['image_mode'] = 'flexible'
        self.assertTrue(core.image_plan_errors(card))
        self.assertIn('도식:', cli.question_instructions('12생과'))
        self.assertNotIn('도식:', cli.question_instructions('12세지'))


if __name__ == '__main__':
    unittest.main()
