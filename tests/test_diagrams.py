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
    'mechanics': dict(track=[[0, 4], [4, 0], [8, 0]], datum=0, objects=[{'kind': 'block', 'on': 1, 'label': 'A', 'id': 'A'}, {'kind': 'ball', 'on': 7, 'label': 'B'}],
                      heights=[{'x': -0.5, 'from': 0, 'to': 4, 'label': '$4h$'}], angles=[{'at': 1, 'label': r'$30^{\circ}$'}],
                      arrows=[{'from': 'A.right', 'dir': -45, 'len': 80, 'label': '$v$'}], walls=[{'x': 8, 'y0': 0, 'y1': 1.5}], ground_label='수평면'),
    'circuit': dict(nodes={'a': [0, 0], 'b': [0, 3], 'c': [4, 3], 'd': [4, 0]},
                    parts=[{'kind': 'battery', 'from': 'a', 'to': 'b', 'label': r'$12\,\mathrm{V}$'}, {'kind': 'resistor', 'from': 'b', 'to': 'c', 'label': '$R$'},
                           {'kind': 'switch', 'from': 'c', 'to': 'd', 'label': '$S$'}, {'kind': 'bulb', 'from': 'd', 'to': 'a'}]),
    'graph': dict(x={'label': '시간', 'ticks': [[1, '$t_{0}$']]}, y={'label': '속력', 'ticks': [[2, '$v_{0}$']]},
                  curves=[{'points': [[0, 2], [1, 1], [2, 0]], 'smooth': True, 'label': 'A'}], guides=[[1, 1]], fills=[{'curve': 0, 'x0': 0, 'x1': 1}]),
    'panels': dict(items=[{'type': 'mechanics', 'caption': '(가)', 'track': [[0, 0], [6, 0]], 'objects': [{'kind': 'cart', 'on': 2, 'label': 'A'}]},
                          {'type': 'graph', 'caption': '(나)', 'curves': [{'points': [[0, 0], [1, 1]]}]}]),
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


    def test_physics_scene_places_objects_on_the_track_and_names_bad_references(self):
        svg, labels = diagrams.render(spec(type='mechanics', **EXAMPLES['mechanics']))
        self.assertIn('url(#groundfade)', svg)
        self.assertTrue(any(l['kind'] == 'physics' and l['text'] == '$4h$' for l in labels))
        self.assertTrue(any(l['text'] == '수평면' for l in labels))
        bad = dict(EXAMPLES['mechanics'], arrows=[{'from': 'Z.top', 'dir': 0}])
        self.assertTrue(any('Z.top' in e for e in diagrams.errors(spec(type='mechanics', **bad))))
        self.assertTrue(any('track' in e for e in diagrams.errors(spec(type='mechanics', track=[[3, 0], [1, 0]]))))
        self.assertTrue(any('kind' in e for e in diagrams.errors(spec(type='circuit', nodes={'a': [0, 0], 'b': [1, 0]}, parts=[{'kind': 'tube', 'from': 'a', 'to': 'b'}]))))

    def test_pulley_string_is_level_with_the_block_and_the_hanging_block_drops_straight(self):
        scene = dict(track=[[0, 4], [8, 4]], base_to=1, objects=[{'kind': 'block', 'on': 3, 'id': 'A', 'label': 'A'}, {'kind': 'block', 'hang': 'P0', 'id': 'B', 'label': 'B'}],
                     pulleys=[{'at': [8.5, 4.4], 'mount': 'corner', 'align': 'A'}], strings=[['A.right', 'P0']])
        svg, labels = diagrams.render(spec(type='mechanics', **scene))
        a = next(l for l in labels if l['text'] == 'A'); b = next(l for l in labels if l['text'] == 'B')
        self.assertGreater(b['y'], a['y'] + 60)
        self.assertIn('A24.0,24.0', svg)          # 줄이 도르래를 감아 돈다

    def test_crowded_particle_panels_shrink_atoms_instead_of_overlapping(self):
        crowded = dict(container='cylinder', panels=[{'molecules': [{'atoms': ['C', 'O', 'O'], 'count': 6}, {'atoms': ['O', 'H', 'H'], 'count': 6}]}])
        svg, _ = diagrams.render(spec(type='particles', **crowded))
        self.assertIn('url(#atom_', svg)
        self.assertEqual(svg.count('<circle'), 6 * 3 + 6 * 3 + 3)


    def test_paper_trims_blank_margins_but_keeps_the_print_scale(self):
        import io
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (3000, 1920), 'white'); ImageDraw.Draw(img).rectangle((600, 800, 2400, 1100), fill='black')
        raw = io.BytesIO(); img.save(raw, format='PNG')
        cut, original = images.trim_margins(raw.getvalue())
        w, h = Image.open(io.BytesIO(cut)).size
        self.assertEqual(original, (3000, 1920)); self.assertLess(h, 600)
        pic = images.picture(cut, 1, 1, original)
        width = int(pic.find('.//SHAPEOBJECT/SIZE').get('Width'))
        self.assertEqual(width, round(29000 * w / 3000))       # 내용은 원래 배율 그대로
        full = Image.new('RGB', (1000, 640), 'black'); raw = io.BytesIO(); full.save(raw, format='PNG')
        self.assertEqual(images.trim_margins(raw.getvalue())[0], raw.getvalue())

    def test_mixed_math_and_unit_labels_become_one_formula_and_hanging_mass_goes_aside(self):
        from app.diagrams_physics import _tex
        self.assertEqual(_tex('$3$ kg'), r'$3\,\mathrm{kg}$')
        self.assertEqual(_tex('정지'), '정지')
        scene = dict(track=[[0, 4], [8, 4]], objects=[{'kind': 'block', 'on': 3, 'id': 'A'}, {'kind': 'block', 'hang': 'P0', 'id': 'B', 'mass': '$1$ kg'}],
                     pulleys=[{'at': [8.5, 4.4], 'align': 'A'}], strings=[['A.right', 'P0']])
        _, labels = diagrams.render(spec(type='mechanics', **scene))
        mass = next(l for l in labels if 'kg' in l['text'])
        self.assertEqual(mass['text'], r'$1\,\mathrm{kg}$')

    def test_prompt_example_is_a_valid_spec_and_sources_compile_without_warnings(self):
        import ast, re, warnings
        m = re.search(r'예: 수평면 위 물체 A와 끝의 도르래에 매단 B → (\{.*?\})\.', diagrams.PROMPT)
        self.assertEqual(diagrams.errors(diagrams.PREFIX + ' ' + m.group(1)), [])
        root = Path(__file__).resolve().parents[1] / 'app'
        for name in ('diagrams.py', 'diagrams_physics.py', 'cli.py'):
            with warnings.catch_warnings():
                warnings.simplefilter('error')
                ast.parse((root / name).read_text(encoding='utf-8'))

    def test_roman_numerals_missing_from_the_hangul_font_become_math_labels(self):
        scene = dict(track=[[0, 6], [8, 0], [12, 0]], zones=[{'x0': 2, 'x1': 4, 'label': '마찰 구간 Ⅱ'}])
        _, labels = diagrams.render(spec(type='mechanics', **scene))
        texts = [(l['kind'], l['text']) for l in labels]
        self.assertIn(('korean', '마찰 구간'), texts)
        self.assertIn(('physics', r'$\mathrm{II}$'), texts)
        self.assertFalse(any('Ⅱ' in t for _, t in texts))

if __name__ == '__main__':
    unittest.main()
