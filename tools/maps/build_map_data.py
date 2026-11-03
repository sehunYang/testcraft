# -*- coding: utf-8 -*-
"""Natural Earth(퍼블릭 도메인)에서 시험지 지도용 바탕 자료를 만든다. 앱에는 줄인 결과만 들어간다.

    python -I tools/maps/build_map_data.py

원본: .runtime/maps/raw/   결과: app/map_data/*.json
"""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / '.runtime/maps/raw'
OUT = ROOT / 'app/map_data'
BASE = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/'
FILES = ['ne_50m_land', 'ne_50m_rivers_lake_centerlines', 'ne_50m_lakes', 'ne_10m_admin_0_countries_kor', 'ne_10m_admin_1_states_provinces']
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)


def fetch(name):
    path = RAW / f'{name}.geojson'
    if not path.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        print('받는 중', name)
        request = urllib.request.Request(BASE + name + '.geojson', headers={'User-Agent': 'TestCraft map data'})
        with urllib.request.urlopen(request, timeout=300) as res: path.write_bytes(res.read())
    return json.loads(path.read_text(encoding='utf-8'))


def simplify(points, tolerance):
    """Douglas-Peucker. 끝점은 남긴다."""
    if len(points) < 3: return points
    keep = [False] * len(points); keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]; bx, by = points[b]
        dx, dy = bx - ax, by - ay; norm = (dx * dx + dy * dy) or 1e-12
        worst, at = 0, None
        for i in range(a + 1, b):
            px, py = points[i]
            t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / norm))
            d = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d > worst: worst, at = d, i
        if at is not None and worst > tolerance * tolerance:
            keep[at] = True; stack += [(a, at), (at, b)]
    return [p for p, k in zip(points, keep) if k]


def rings(geometry):
    kind, coords = geometry['type'], geometry['coordinates']
    if kind == 'Polygon': return [coords[0]]
    if kind == 'MultiPolygon': return [poly[0] for poly in coords]
    if kind == 'LineString': return [coords]
    if kind == 'MultiLineString': return coords
    return []


def compact(geometry, tolerance, digits, minimum=3):
    out = []
    for ring in rings(geometry):
        thin = simplify([tuple(p[:2]) for p in ring], tolerance)
        if len(thin) >= minimum: out.append([[round(x, digits), round(y, digits)] for x, y in thin])
    return out


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f'{name}.json'
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(name, path.stat().st_size // 1024, 'KB')


def main():
    write('land', compact_all(fetch('ne_50m_land'), 0.02))
    write('lakes', compact_all(fetch('ne_50m_lakes'), 0.04))
    rivers = []
    for f in fetch('ne_50m_rivers_lake_centerlines')['features']:
        rivers += compact(f['geometry'], 0.08, 2, minimum=2)
    write('rivers', rivers)
    countries = {}
    for f in fetch('ne_10m_admin_0_countries_kor')['features']:
        p = f['properties']
        code = p['ADM0_A3_KO'] if p.get('ADM0_A3_KO') not in (None, '-99') else p['ADM0_A3']
        # 한국 지도에 함께 나오는 나라는 확대해도 각지지 않게 더 촘촘히 둔다
        lines = compact(f['geometry'], 0.012 if code in ('JPN', 'CHN', 'RUS') else 0.04, 3 if code in ('JPN', 'CHN', 'RUS') else 2)
        if lines:
            countries[code] = {'name': p.get('NAME_KO') or p.get('NAME'), 'en': p.get('NAME_EN') or p.get('NAME'), 'rings': lines}
    write('countries', countries)
    provinces = {}
    for f in fetch('ne_10m_admin_1_states_provinces')['features']:
        p = f['properties']
        if p.get('adm0_a3') not in ('KOR', 'PRK'): continue
        lines = compact(f['geometry'], 0.01, 3)
        if lines:
            name = p.get('name_ko') or p['name']
            # 남북에 같은 이름이 있고, 남쪽은 이름이 바뀐 곳이 있다
            if p['adm0_a3'] == 'PRK' and name in ('강원도',): name += '(북한)'
            name = {'강원도': '강원특별자치도', '전라북도': '전북특별자치도'}.get(name, name)
            provinces[name] = {'country': p['adm0_a3'], 'en': p['name'], 'rings': lines}
    write('korea_provinces', provinces)


def compact_all(collection, tolerance):
    out = []
    for f in collection['features']: out += compact(f['geometry'], tolerance, 2)
    return out


if __name__ == '__main__':
    main()
