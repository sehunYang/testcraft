import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import core, images, maps


def spec(**fields):
    return maps.PREFIX + ' ' + json.dumps(fields, ensure_ascii=False)


class MapTests(unittest.TestCase):
    def test_map_is_a_valid_strict_drawing_with_labels_in_their_own_layer(self):
        svg, labels = maps.render(spec(view='mediterranean', points=[{'at': [14.3, 40.8], 'label': 'A'}], routes=[{'path': [[29, 41], [10, 37]], 'label': '❶'}]))
        images.validate_mode_layers(svg, 'strict')
        self.assertNotIn('<text', svg)
        self.assertEqual({x['text'] for x in labels}, {'A', '1'})     # 원문자는 글꼴에 없어 동그라미를 그림으로 그린다
        self.assertIn('r="16"', svg)

    def test_history_map_has_no_modern_borders_unless_asked(self):
        plain, _ = maps.render(spec(view='europe'))
        bordered, _ = maps.render(spec(view='europe', borders=True))
        self.assertGreater(plain.count('<path') * 5, 0)
        self.assertGreater(bordered.count('<path'), plain.count('<path') * 5)

    def test_shading_soft_blobs_and_scale_bar(self):
        svg, labels = maps.render(spec(view='south_korea', shade=[{'provinces': ['강원특별자치도'], 'label': '(가)', 'pattern': 'hatch'}], blobs=[{'at': [127, 36], 'radius': [1, 1], 'label': '(나)'}], scale_km=100))
        images.validate_svg(svg)
        self.assertIn('radialGradient', svg)
        self.assertEqual({x['text'] for x in labels}, {'(가)', '(나)', '0', '100km'})

    def test_pacific_view_crosses_the_date_line(self):
        svg, labels = maps.render(spec(view='pacific', points=[{'at': [-120, 35], 'label': 'C'}]))
        images.validate_svg(svg)
        self.assertGreater(labels[0]['x'], 500)

    def test_view_can_be_given_as_a_box(self):
        self.assertEqual(maps.errors(spec(view=[20, 5, 95, 50])), [])
        svg, labels = maps.render(spec(view=[20, 5, 95, 50], blobs=[{'at': [70, 30], 'radius': [8, 5], 'label': '(가)'}]))
        images.validate_svg(svg)

    def test_mistakes_are_named_for_the_teacher(self):
        self.assertTrue(any('view' in e for e in maps.errors(spec(view='mars'))))
        self.assertTrue(any('XXX' in e for e in maps.errors(spec(view='world', shade=[{'countries': ['XXX']}]))))
        self.assertTrue(any('JSON' in e for e in maps.errors(maps.PREFIX + ' {')))
        self.assertTrue(any('범위 밖' in e for e in maps.errors(spec(view=[20, 5, 95, 50], blobs=[{'at': [116, 40], 'label': '(가)'}]))))
        with self.assertRaises(ValueError): maps.render(spec(view='mars'))

    def test_editor_preview_gives_projection_and_keeps_the_base_map_when_a_mark_is_wrong(self):
        good = maps.preview(spec(view='europe', points=[{'at': [2.3, 48.9], 'label': 'A'}]))
        self.assertEqual(good['errors'], [])
        p = good['projection']
        x = 500 + (2.3 - p['cx']) * p['k'] * p['s']
        self.assertAlmostEqual(x, maps._Projection(maps.VIEWS['europe'])(2.3, 48.9)[0])
        outside = maps.preview(spec(view='europe', points=[{'at': [127, 37], 'label': 'A'}]))
        self.assertTrue(any('범위 밖' in e for e in outside['errors']))
        self.assertIn('<svg', outside['svg'])                       # 교사가 표시를 끌어 들일 수 있게 바탕은 그린다
        self.assertNotIn('svg', maps.preview(spec(view='mars')))
        self.assertNotIn('svg', maps.preview('지도: {'))

    def test_editor_options_name_countries_in_korean(self):
        options = maps.options()
        self.assertEqual(options['countries']['FRA'], '프랑스')
        self.assertIn('강원특별자치도', options['provinces'])
        self.assertIn('europe', options['views'])

    def test_past_polities_are_found_by_year_in_english_or_korean(self):
        names = {p['name']: p['ko'] for p in maps.polities(500)}
        self.assertEqual(names['Goguryeo'], '고구려')
        self.assertNotIn('Joseon', names)
        self.assertEqual({p['name']: p['ko'] for p in maps.polities(1500)}['Joseon'], '조선')
        svg, labels = maps.render(spec(view='korea', year=500, past_borders=True, shade=[{'polities': ['고구려'], 'label': '(가)', 'pattern': 'hatch'}]))
        images.validate_svg(svg)
        self.assertEqual([x['text'] for x in labels], ['(가)'])
        self.assertNotIn('#555555" stroke-width="0.7"', svg)          # 역사 지도에는 현대 시·도 경계를 그리지 않는다

    def test_every_past_polity_has_a_korean_name_unique_within_its_year(self):
        data = maps._load('history')
        self.assertEqual([n[0] for n in data['names'] if not n[1]], [])
        self.assertFalse(any(ch.isascii() and ch.isalpha() for n in data['names'] for ch in n[1]))     # 로마자를 남기지 않는다
        for year in (-500, 117, 750, 1200, 1500, 1800, 1900):
            names = [p['ko'] for p in maps.polities(year)]
            self.assertEqual(len(names), len(set(names)), year)

    def test_past_map_mistakes_are_named(self):
        self.assertTrue(any('Roman Empire' in e for e in maps.errors(spec(view='europe', year=117, shade=[{'polities': ['Roman Empir']}]))))
        self.assertTrue(any('연도(year)와 함께' in e for e in maps.errors(spec(view='europe', shade=[{'polities': ['Roman Empire']}]))))
        self.assertTrue(any('현대 자료' in e for e in maps.errors(spec(view='europe', year=117, borders=True))))
        self.assertTrue(any('정수' in e for e in maps.errors(spec(view='europe', year=3000))))

    def test_geologic_era_maps_fill_the_globe_without_modern_layers(self):
        svg, _ = maps.render(spec(view='globe', ma=250, lines=[{'lat': 0}]))
        images.validate_svg(svg)
        self.assertLess(len(svg), 1_000_000)
        problems = maps.errors(spec(view='globe', ma=251, borders=True))
        self.assertTrue(any('250Ma' in e for e in problems))
        self.assertTrue(any('borders' in e for e in problems))
        self.assertEqual(maps._Projection(maps.VIEWS['globe'])(180, -85), (994.0, 634.0))

    def test_districts_draw_shared_lines_once_and_shade_by_short_or_full_name(self):
        svg, labels = maps.render(spec(view='south_korea', districts=True, shade=[{'districts': ['춘천시'], 'label': '(가)'}, {'districts': ['부산광역시 중구'], 'label': '(나)'}]))
        images.validate_svg(svg)
        self.assertLess(len(svg), 1_000_000)
        self.assertIn('stroke="#8c8c8c" stroke-width="0.5"', svg)
        self.assertEqual([x['text'] for x in labels], ['(가)', '(나)'])
        self.assertEqual(maps._find_district('광주광역시 동구'), '전남광주통합특별시 동구')      # 통합 전 시·도 이름으로도 찾는다
        self.assertTrue(any('여러 곳' in e and '부산광역시 중구' in e for e in maps.errors(spec(view='south_korea', shade=[{'districts': ['중구']}]))))
        self.assertTrue(any('시·군·구 경계' in e for e in maps.errors(spec(view='korea', year=1900, districts=True))))
        self.assertIn('광주광역시', maps.options()['provinces'])

    def test_callout_box_points_its_tail_at_the_place_and_keeps_text_in_the_label_layer(self):
        svg, labels = maps.render(spec(view='south_korea', callouts=[{'at': [129.07, 35.18], 'text': '항만 물동량이\n가장 많다.', 'offset': [-200, -120]}]))
        self.assertEqual([x['text'] for x in labels], ['항만 물동량이', '가장 많다.'])
        project = maps._Projection(maps.VIEWS['south_korea']); x, y = project(129.07, 35.18)
        self.assertIn(f'L{x:.1f},{y:.1f}L', svg)                      # 꼬리 끝이 그 위치다
        self.assertTrue(any('글(text)' in e for e in maps.errors(spec(view='world', callouts=[{'at': [0, 0], 'text': ' '}]))))

    def test_present_positions_move_with_their_plate_to_the_geologic_era(self):
        self.assertEqual(maps.to_past(127, 37.5, 0), [127.0, 37.5])
        seoul = maps.to_past(127, 37.5, 250)
        self.assertGreater(abs(seoul[0] - 127) + abs(seoul[1] - 37.5), 10)
        margin = maps._load('paleo')['margin']['250']
        self.assertTrue(any(maps._inside(*seoul, ring) for ring in margin))       # 그때 대륙 위에 놓인다
        locked = spec(view='globe', ma=250, points=[{'at': [127, 37.5], 'present': True, 'label': 'A'}])
        svg, labels = maps.render(locked)
        x, y = maps._Projection(maps.VIEWS['globe'])(*seoul)
        self.assertIn(f'cx="{x:.1f}" cy="{y:.1f}"', svg)
        turns = maps.preview(locked)['turns']['points:0']
        self.assertEqual(len(turns), 1)
        self.assertTrue(any('ma' in e for e in maps.errors(spec(view='world', points=[{'at': [127, 37.5], 'present': True}]))))

    def test_latex_labels_from_the_ai_print_as_plain_text(self):
        locked = maps.PREFIX + r' {"view":"world","lines":[{"lat":0,"label":"$0^{\circ}$"}],"points":[{"at":[0,10],"label":"$A$"}]}'
        self.assertEqual(maps.errors(locked), [])
        self.assertEqual([x['text'] for x in maps.render(locked)[1]], ['0°', 'A'])

    def test_plan_check_accepts_a_map_without_text_prompts(self):
        card = core.blank_card(1); card.update(data_kind='image', image_mode='strict', image_locked=spec(view='world', points=[{'at': [0, 0], 'label': 'A'}]))
        self.assertEqual(core.image_plan_errors(card), [])
        card['image_locked'] = spec(view='mars')
        self.assertTrue(core.image_plan_errors(card))


if __name__ == '__main__':
    unittest.main()
