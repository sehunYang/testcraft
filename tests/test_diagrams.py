import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.runtime/packages'))
from app import cli, core, diagrams, diagrams_physics, images


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
    'chart': dict(chart='bar', categories=['2000년', '2020년'], series=[{'name': 'A국', 'values': [12, 25]},
                  {'name': '인구 밀도', 'values': [300, 420], 'as': 'line', 'axis': 'right'}], y={'label': '(%)'}, y2={'label': '(명/㎢)'}, values=True),
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
        self.assertNotIn('가계도', cli.question_instructions('12세지'))      # 사회에는 수치 그래프 도식만 간다


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
        scene = dict(track=[[0, 4], [8, 4]], base_to=1, objects=[{'kind': 'block', 'on': 3, 'id': 'A', 'label': '$A$'}, {'kind': 'block', 'hang': 'P0', 'id': 'B', 'label': '$B$'}],
                     pulleys=[{'at': [8.5, 4.4], 'mount': 'corner', 'align': 'A'}], strings=[['A.right', 'P0']])
        svg, labels = diagrams.render(spec(type='mechanics', **scene))
        a = next(l for l in labels if l['text'] == '$A$'); b = next(l for l in labels if l['text'] == '$B$')
        self.assertGreater(b['y'], a['y'] + 60)
        self.assertRegex(svg, r'A(\d+\.\d),\1 0 0 1')          # 줄이 도르래를 감아 돈다(반지름은 물체 크기를 따라 커진다)
        block = re.search(r'M([\d.]+),([\d.]+)L([\d.]+),\2L\3,([\d.]+)L\1,\4Z" fill="white"', svg)    # 물체 A
        glyph_w, glyph_h = diagrams_physics._measure('$A$', a['size'])
        self.assertAlmostEqual(a['x'] + glyph_w / 2, (float(block[1]) + float(block[3])) / 2, delta=1)    # 이름 글자는 물체 한가운데
        self.assertAlmostEqual(a['y'] + glyph_h / 2, (float(block[2]) + float(block[4])) / 2, delta=1)

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

    def test_app_drawn_figures_convert_to_editable_objects_with_their_shading(self):
        import hashlib
        from app import vectors
        for kind, fields in (('mechanics', EXAMPLES['mechanics']), ('particles', EXAMPLES['particles'])):
            with self.subTest(kind):
                svg, _ = diagrams.render(spec(type=kind, **fields))
                scene = vectors.from_svg(svg, hashlib.sha256(svg.encode()).hexdigest())
                self.assertTrue(scene['objects'])
                self.assertIn('Gradient', scene['defs'])

    def test_charts_draw_every_form_and_go_to_social_and_science_prompts_only(self):
        forms = {
            'line': dict(chart='line', categories=['1970', '2020'], series=[{'name': '출생률', 'values': [31, None]}], y={'label': '(‰)'}, x={'label': '(년)'}),
            'pie': dict(chart='pie', slices=[{'name': '1차', 'value': 5}, {'name': '3차', 'value': 95}], title='(가) 지역'),
            'band': dict(chart='band', categories=['1990년'], series=[{'name': '유소년층', 'values': [30]}, {'name': '노년층', 'values': [70]}]),
            'scatter': dict(chart='scatter', points=[{'label': 'A', 'x': 2, 'y': 80}], y={'label': '도시화율(%)', 'ticks': False}),
        }
        for name, fields in forms.items():
            with self.subTest(name):
                svg, labels = diagrams.render(spec(type='chart', **fields))
                images.validate_mode_layers(svg, 'strict')
                self.assertNotIn('<text', svg)
                self.assertFalse(any(ch in l['text'] for l in labels if l['kind'] == 'korean' for ch in '‰㎢℃'))
        _, labels = diagrams.render(spec(type='chart', **forms['line']))
        self.assertIn(('physics', '$‰$'), [(l['kind'], l['text']) for l in labels])     # 한글 글꼴에 없는 기호는 수식 글씨로
        _, labels = diagrams.render(spec(type='chart', **EXAMPLES['chart']))
        self.assertIn('(명/km²)', [l['text'] for l in labels])
        twin = dict(items=[{'type': 'chart', **forms['pie'], 'caption': '(가)'}, {'type': 'chart', **forms['pie'], 'caption': '(나)'}])
        self.assertEqual(diagrams.errors(spec(type='panels', **twin)), [])
        self.assertTrue(any('합이' in e for e in diagrams.errors(spec(type='chart', chart='band', categories=['a'], series=[{'name': 'x', 'values': [40]}]))))
        self.assertTrue(any('개수' in e for e in diagrams.errors(spec(type='chart', chart='bar', categories=['a', 'b'], series=[{'name': 'x', 'values': [1]}]))))
        self.assertTrue(any('chart' in e for e in diagrams.errors(spec(type='chart', chart='radar'))))
        # 2026-11-13: 한글과 수식이 섞인 축 이름("힘의 $x$성분")은 한글·수식 조각으로 나뉜다(수식 글씨 속 한글은 승인에서 거부됨)
        _, labels = diagrams.render(spec(type='graph', x={'label': '시간(ms)'}, y={'label': '힘의 $x$성분(kN)'}, curves=[{'points': [[0, 0], [1, 4]]}]))
        self.assertFalse([l for l in labels if l['kind'] == 'physics' and any('가' <= ch <= '힣' for ch in l['text'])])
        self.assertIn(('physics', '$x$'), [(l['kind'], l['text']) for l in labels])
        _, labels = diagrams.render(spec(type='sequence', strands=[{'label': 'DNA 주형 가닥', 'seq': 'TACG'}]))
        self.assertTrue(all(str(l['text']).strip() for l in labels))          # 빈 글씨가 없어야 출력된다
        _, labels = diagrams.render(spec(type='chart', chart='scatter', lines=[{'name': '', 'points': [[0, 0], [1, 2]]}], x={'label': '빛의 세기(lx)'}))
        self.assertIn('빛의 세기(lux)', [l['text'] for l in labels])           # 교사 지정: lx가 아니라 lux
        # 2026-11-13: 세로축을 물결로 자르면 자른 구간의 눈금은 빠지고 아래쪽 눈금 간격이 넓어진다
        broken = spec(type='chart', chart='scatter', lines=[{'name': '', 'points': [[0, -70], [1, 30], [3, -80]]}],
                      y={'min': -80, 'max': 40, 'break': [-65, -5], 'ticks': [-80, -75, -70, -40, 0, 30]})
        self.assertEqual(diagrams.errors(broken), [])
        svg, labels = diagrams.render(broken)
        texts = [l['text'] for l in labels]
        self.assertIn('-75', texts); self.assertNotIn('-40', texts)
        ys = {l['text']: l['y'] for l in labels if l['text'] in ('-80', '-75', '-70')}
        self.assertGreater(ys['-80'] - ys['-70'], 40)                      # 접지 않으면 약 20px밖에 안 된다
        # 그래프 전체를 자른다: 선은 자를 값에서 나뉘어 실제 기울기로 띠 가장자리에 닿고, 띠는 그림 폭 전체를 지운다
        from app import diagrams_chart as ch
        self.assertEqual(ch._split_at([(0, -70), (100, 30)], [-65, -5]), [(0, -70), (5.0, -65), (65.0, -5), (100, 30)])
        self.assertIn('fill="white"', svg)
        # 2026-11-13: (가)(나) 나란히 출력에서 앱 도식은 손대지 않았을 때만 반 폭으로 다시 그린다(옮긴 글씨를 지킨다)
        from app import images as imgs, labels as lab
        locked = spec(type='chart', chart='bar', categories=['a', 'b'], series=[{'name': 'x', 'values': [1, 2]}])
        drawn = lab.normalize_labels([dict(o, id=f'{k:016x}') for k, o in enumerate(diagrams.render(locked)[1])])
        block = {'kind': 'image', 'image_locked': locked, 'image_labels': drawn}
        self.assertTrue(imgs.untouched(block))
        self.assertFalse(imgs.untouched({**block, 'image_labels': [dict(drawn[0], x=drawn[0]['x'] + 15)] + drawn[1:]}))
        self.assertFalse(imgs.untouched({**block, 'image_labels': drawn[1:]}))                 # 글씨를 지웠다
        self.assertFalse(imgs.untouched({**block, 'image_scene': {'objects': []}}))            # 그림 객체를 편집했다
        self.assertFalse(imgs.untouched({'kind': 'image', 'image_locked': 'SVG 규칙…', 'image_labels': []}))   # AI 그림
        days = [str(d) for d in range(0, 40, 2)]                      # 2026-11-13: 시간에 따른 꺾은선은 20칸도 그린다
        self.assertEqual(diagrams.errors(spec(type='chart', chart='line', categories=days, series=[{'name': '항체', 'values': list(range(20))}])), [])
        self.assertTrue(any('12개' in e for e in diagrams.errors(spec(type='chart', chart='bar', categories=days, series=[{'name': '항체', 'values': list(range(20))}]))))
        self.assertIn('"chart":"bar"', cli.question_instructions('12세지'))
        self.assertIn('표가 맞는 경우', cli.question_instructions('12생과'))
        self.assertNotIn('"chart":"bar"', cli.question_instructions('12문학'))
        english = cli.question_instructions('12영Ⅰ')          # 영어 도표 문항(2026-11-12)
        self.assertIn('"chart":"bar"', english); self.assertIn('영어 도표 문항', english)

    def test_math_function_graphs_follow_the_formula_with_open_and_closed_ends(self):
        from app import diagrams_function as fn
        self.assertEqual(fn.compile_expr('2^x + log(8, 2) - abs(-1)')(3), 10)
        self.assertAlmostEqual(fn.compile_expr('x**(1/3)')(-8), -2)
        self.assertEqual(fn.compile_expr('floor(x)')(1.5), 1)
        for bad in ('__import__("os")', 'x.real', 'y+1', 'open(x)'):
            with self.subTest(bad), self.assertRaises(ValueError): fn.compile_expr(bad)
        steps = dict(view=[-1, 3.5, -1.5, 3.5], curves=[{'expr': 'floor(x)', 'domain': [k, k + 1], 'ends': ['closed', 'open']} for k in (-1, 0, 1, 2)])
        svg, labels = diagrams.render(spec(type='function', **steps))
        images.validate_mode_layers(svg, 'strict')
        self.assertEqual(svg.count('fill="white" stroke="#111111" stroke-width="2.2"'), 4)          # 빈 점은 계단 오른쪽 끝마다
        self.assertEqual({'$x$', '$y$', '$O$'}, {l['text'] for l in labels})
        frame = fn.Frame([-1, 3.5, -1.5, 3.5], fn.FRAME, False)
        for run in fn._runs(fn.compile_expr('floor(x)'), -1, 3, frame):
            self.assertEqual(len({round(y, 6) for _, y in run}), 1)                                   # 계단 사이를 세로선으로 잇지 않는다
        self.assertEqual(len(fn._runs(fn.compile_expr('tan(x)'), -3, 3, fn.Frame([-3, 3, -4, 4], fn.FRAME, False))), 3)
        self.assertTrue(any('view' in e for e in diagrams.errors(spec(type='function', curves=[{'expr': 'x'}]))))
        self.assertTrue(any('허용하지' in e for e in diagrams.errors(spec(type='function', view=[0, 1, 0, 1], curves=[{'expr': 'eval(x)'}]))))
        twin = dict(items=[{'type': 'function', 'view': [-2, 2, -1, 3], 'curves': [{'expr': 'abs(x)'}], 'caption': '(가)'}] * 2)
        self.assertEqual(diagrams.errors(spec(type='panels', **twin)), [])
        self.assertIn('"type":"function"', cli.question_instructions('12대수'))
        self.assertNotIn('"type":"function"', cli.question_instructions('12물리'))

    def test_small_ai_json_slips_are_repaired_and_stored_clean(self):
        bad = '도식: {"type":"mechanics","track":[[0,4.5],[3.5,0],[8,0]],"heights":[{"x":-0.7,"from":0,"to":4.5,"label":"$0.45$ m,"x_to":0}]}'
        self.assertEqual(diagrams.errors(bad), [])
        clean = diagrams.canonical(bad)
        self.assertEqual(diagrams.spec_of(clean)['heights'][0]['label'], '$0.45$ m')
        self.assertTrue(any('JSON' in e for e in diagrams.errors('도식: {"type":"mechanics","track":[[0,1]')))

if __name__ == '__main__':
    unittest.main()
