"""시험지 지도. Natural Earth 좌표를 평가원 지도 관례의 흑백 선화 SVG로 그린다.

그림 규칙(image_locked)이 "지도: {JSON}" 으로 시작하면 AI가 그리지 않고 이 모듈이 그린다. 해안선이 정확해야 하기 때문이다.
글씨는 다른 그림처럼 글씨 레이어로 분리한다.
"""
import difflib
import gzip
import json
import math
from functools import lru_cache
from pathlib import Path
import re

DATA = Path(__file__).resolve().parent / 'map_data'
PREFIX = '지도:'
W, H, MARGIN = 1000, 640, 6
LAND, DARK, LINE = '#d9d9d9', '#8c8c8c', '#222222'
VIEWS = {
    'world': (-170, -58, 180, 78), 'east_asia': (95, 18, 150, 55), 'korea': (123.5, 33, 131.5, 43.2), 'south_korea': (125, 33, 130.5, 38.9),
    'japan': (127, 30, 147, 46), 'china': (73, 18, 135, 54), 'southeast_asia': (90, -12, 130, 28), 'south_asia': (60, 5, 100, 38),
    'central_asia': (45, 30, 90, 55), 'silk_road': (10, 15, 130, 55), 'middle_east': (25, 10, 70, 45), 'mediterranean': (-10, 28, 42, 48),
    'europe': (-12, 34, 45, 62), 'africa': (-20, -36, 55, 38), 'north_america': (-130, 10, -60, 55), 'south_america': (-85, -56, -32, 14),
    'oceania': (110, -48, 180, 0), 'atlantic': (-100, -40, 40, 65), 'indian_ocean': (30, -35, 125, 30), 'pacific': (100, -50, 290, 65),
    'globe': (-180, -85, 180, 85),
}
PATTERNS = ('gray', 'dark', 'hatch', 'white')
PALEO_KINDS = ('margin', 'coast')      # 대륙붕까지 포함한 대륙 / 당시 해안선
YEARS = (-3400, 2024)
CIRCLED = {c: str(i + 1) for i, c in enumerate('①②③④⑤⑥⑦⑧⑨⑩')} | {c: str(i + 1) for i, c in enumerate('❶❷❸❹❺❻❼❽❾❿')}


@lru_cache(maxsize=8)
def _load(name):
    path = DATA / f'{name}.json'
    if path.exists(): return json.loads(path.read_text(encoding='utf-8'))
    return json.loads(gzip.decompress((DATA / f'{name}.json.gz').read_bytes()))


def paleo_ages():
    return _load('paleo')['ages']


def _unpack(flat, step):
    """저장한 고리는 1/step도 단위 차분이다."""
    x, y = flat[0], flat[1]; out = [(x / step, y / step)]
    for i in range(2, len(flat), 2):
        x += flat[i]; y += flat[i + 1]; out.append((x / step, y / step))
    return out


@lru_cache(maxsize=4096)
def _history_ring(index):
    """역사 국경 고리는 겹치는 것을 한 번만 저장해 두었다."""
    data = _load('history')
    return _unpack(data['rings'][index], data['step'])


@lru_cache(maxsize=512)
def _korea_rings(kind, name):
    """남한 시·도와 시·군·구는 통계청 경계로 그린다. 이웃끼리 경계선이 정확히 겹친다."""
    data = _load('korea_districts')
    return [_unpack(flat, data['step']) for flat in data[kind][name]['rings']]


def _province_rings(name):
    if name in _load('korea_districts')['provinces']: return _korea_rings('provinces', name)
    return _load('korea_provinces')[name]['rings']


def _province_names():
    """편집 화면 순서: 남한의 현재 시·도, 통합 전 이름, 북한 도."""
    korea = _load('korea_districts')['provinces']
    return ([n for n, p in korea.items() if 'merged_into' not in p] + [n for n, p in korea.items() if 'merged_into' in p]
            + [n for n, p in _load('korea_provinces').items() if p['country'] == 'PRK'])


def _find_district(name):
    """'강원특별자치도 춘천시' 또는 겹치지 않는 '춘천시'. 통합 전 시·도 이름으로 적어도 찾는다."""
    data = _load('korea_districts')
    districts = data['districts']
    if name in districts: return name
    sido, _, rest = str(name).partition(' ')
    merged = data['provinces'].get(sido, {}).get('merged_into')
    if rest and merged and f'{merged} {rest}' in districts: return f'{merged} {rest}'
    same = [key for key, d in districts.items() if d['name'] == name]
    return same[0] if len(same) == 1 else None


@lru_cache(maxsize=64)
def _polities_at(year):
    """그해에 있던 나라. {영어 이름: (한국어 이름, 고리 번호들)}"""
    data = _load('history')
    return {data['names'][i][0]: (data['names'][i][1], ids) for i, start, end, ids in data['rows'] if start <= year <= end}


def polities(year):
    """편집 화면의 나라 목록. 괄호로 싼 이름은 속한 나라를 모두 합친 범위다."""
    items = [{'name': name, 'ko': ko} for name, (ko, _) in _polities_at(int(year)).items()]
    return sorted(items, key=lambda x: (x['name'].startswith('('), not x['ko'], x['ko'] or x['name']))


def _find_polity(name, year):
    found = _polities_at(year)
    if name in found: return name
    return next((en for en, (ko, _) in found.items() if ko and ko == name), None)


@lru_cache(maxsize=1)
def _plates():
    """판 다각형(지금 위치)과 판별 회전 묶음. 회전은 PALEOMAP 판 모형으로 지질시대 해안선과 같은 모형이다."""
    data = _load('plates')
    polys = []
    for plate, begin, end, flat in data['polygons']:
        ring = _unpack(flat, data['step'])
        # 날짜변경선을 넘는 판(태평양판 등)은 경도를 이어 붙여야 평면 안팎 판정이 맞는다
        for i in range(1, len(ring)):
            lon = ring[i][0]
            while lon - ring[i - 1][0] > 180: lon -= 360
            while lon - ring[i - 1][0] < -180: lon += 360
            ring[i] = (lon, ring[i][1])
        if abs(ring[-1][0] - ring[0][0]) > 180:       # 극을 둘러싼 판(남극판 등)은 극을 지나 닫는다
            pole = -90 if sum(p[1] for p in ring) < 0 else 90
            ring += [(ring[-1][0], pole), (ring[0][0], pole)]
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        polys.append((plate, begin, end, (min(xs), min(ys), max(xs), max(ys)), ring))
    seqs = {}
    for moving, fixed, rows in data['rotations']: seqs.setdefault(moving, []).append((fixed, rows))
    return polys, seqs


def _inside(x, y, ring):
    hit = False
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0): hit = not hit
    return hit


def _plate_of(lon, lat, ma):
    """지금 그 자리를 덮는 판 다각형 가운데 ma에 쓸 수 있는 것의 판 번호. 다각형마다 쓸 수 있는 기간이 있다."""
    found = [(plate, begin, end) for plate, begin, end, box, ring in _plates()[0]
             if any(box[0] <= x <= box[2] and box[1] <= lat <= box[3] and _inside(x, lat, ring) for x in (lon, lon - 360, lon + 360))]
    for plate, begin, end in found:
        if (begin is None or begin >= ma) and (end is None or end <= ma): return plate, None
    return None, max((b for _, b, _ in found if b is not None), default=None) if found else None


def _quat(lat, lon, angle):
    la, lo, h = math.radians(lat), math.radians(lon), math.radians(angle) / 2
    s = math.sin(h)
    return (math.cos(h), s * math.cos(la) * math.cos(lo), s * math.cos(la) * math.sin(lo), s * math.sin(la))


def _qmul(a, b):
    w0, x0, y0, z0 = a; w1, x1, y1, z1 = b
    return (w0 * w1 - x0 * x1 - y0 * y1 - z0 * z1, w0 * x1 + x0 * w1 + y0 * z1 - z0 * y1,
            w0 * y1 - x0 * z1 + y0 * w1 + z0 * x1, w0 * z1 + x0 * y1 - y0 * x1 + z0 * w1)


def _slerp(a, b, f):
    dot = sum(p * q for p, q in zip(a, b))
    if dot < 0: b, dot = tuple(-q for q in b), -dot
    if dot > 0.9995: q = tuple(p + f * (r - p) for p, r in zip(a, b))
    else:
        t = math.acos(dot); sa, sb = math.sin((1 - f) * t) / math.sin(t), math.sin(f * t) / math.sin(t)
        q = tuple(sa * p + sb * r for p, r in zip(a, b))
    n = math.sqrt(sum(p * p for p in q))
    return tuple(p / n for p in q)


@lru_cache(maxsize=4096)
def _rotation(plate, ma):
    """판의 지금→그때 회전. 기준 판의 회전에 상대 회전을 잇는다(판 0이 기준)."""
    if plate == 0: return (1.0, 0.0, 0.0, 0.0)
    for fixed, rows in _plates()[1].get(plate, []):
        if rows[0][0] <= ma <= rows[-1][0]:
            for a, b in zip(rows, rows[1:] or rows):
                if a[0] <= ma <= b[0]:
                    f = (ma - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0
                    return _qmul(_rotation(fixed, ma), _slerp(_quat(*a[1:]), _quat(*b[1:]), f))
    raise ValueError(f'판 {plate}의 {ma}Ma 회전 자료가 없습니다.')


def _rotate(q, lon, lat):
    la, lo = math.radians(lat), math.radians(lon)
    v = (0.0, math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
    _, x, y, z = _qmul(_qmul(q, v), (q[0], -q[1], -q[2], -q[3]))
    return [round(math.degrees(math.atan2(y, x)), 2), round(math.degrees(math.asin(max(-1.0, min(1.0, z)))), 2)]


def _past(lon, lat, ma):
    plate, since = _plate_of(lon, lat, ma)
    if plate is None and since is not None: raise ValueError(f'[{lon}, {lat}]는 {ma}Ma에 아직 생기지 않은 땅입니다(약 {since:g}Ma 이후).')
    if plate is None: raise ValueError(f'[{lon}, {lat}]는 판 자료에서 찾지 못한 위치입니다.')
    q = _rotation(plate, ma)
    return _rotate(q, lon, lat), q


def to_past(lon, lat, ma):
    """지금의 경위도를 ma백만 년 전 위치로 옮긴다. 그 땅이 그때 없었으면 ValueError."""
    return _past(lon, lat, ma)[0]


MOVABLE = {'points': 'at', 'blobs': 'at', 'callouts': 'at', 'routes': 'path', 'areas': 'points'}


def _present(spec, turns=None):
    """present: true인 표시는 지금의 경위도로 적은 것이다. 지질시대 지도에 그릴 때 그때 위치로 옮긴다.
    turns에는 편집 화면이 끌어 옮긴 위치를 지금 좌표로 되돌릴 회전을 모은다."""
    ma = spec.get('ma')
    if ma is None or not any(item.get('present') for group in MOVABLE for item in spec.get(group, [])): return spec
    spec = json.loads(json.dumps(spec))
    for group, key in MOVABLE.items():
        for i, item in enumerate(spec.get(group, [])):
            if not item.get('present'): continue
            moved = [_past(*p, ma) for p in ([item[key]] if key == 'at' else item[key])]
            item[key] = moved[0][0] if key == 'at' else [m[0] for m in moved]
            if turns is not None: turns[f'{group}:{i}'] = [list(m[1]) for m in moved]
    return spec


def _year_text(year):
    return f'기원전 {-year}년' if year < 0 else f'{year}년'


def is_map(locked):
    return str(locked or '').strip().startswith(PREFIX)


def spec_of(locked):
    text = str(locked or '').strip()
    if not text.startswith(PREFIX): raise ValueError('지도 명세가 아닙니다.')
    body = text[len(PREFIX):]
    try:
        spec = json.loads(body)
    except ValueError as e:
        try:        # AI가 글씨에 LaTeX(\circ 등)를 쓰면 JSON에 없는 이스케이프가 된다. 백슬래시를 글자로 읽는다.
            spec = json.loads(re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', body))
        except ValueError:
            raise ValueError(f'지도 명세의 JSON 오류: {e}') from None
    if not isinstance(spec, dict): raise ValueError('지도 명세는 JSON 객체여야 합니다.')
    return spec


def errors(locked):
    """지도 명세에서 그리기 전에 알 수 있는 오류. 교사가 고칠 수 있게 항목을 짚어 준다."""
    try:
        spec = spec_of(locked)
    except ValueError as e:
        return [str(e)]
    out = []
    view = spec.get('view')
    if not ((isinstance(view, str) and view in VIEWS) or (isinstance(view, list) and len(view) == 4 and all(isinstance(v, (int, float)) for v in view))):
        out.append('지도 범위(view)는 ' + ', '.join(VIEWS) + ' 중 하나이거나 [서경/동경, 남위/북위, …] 네 숫자여야 합니다.')
    year, ma = spec.get('year'), spec.get('ma')
    if year is not None and not (isinstance(year, int) and not isinstance(year, bool) and YEARS[0] <= year <= YEARS[1]):
        out.append(f'연도(year)는 {YEARS[0]}~{YEARS[1]} 사이의 정수입니다. 기원전은 음수로 씁니다.')
        year = None
    if ma is not None:
        ages = paleo_ages()
        if ma not in ages:
            near = min(ages, key=lambda a: abs(a - ma)) if isinstance(ma, (int, float)) else 250
            out.append(f'지질시대(ma) {ma}Ma 자료는 없습니다. 가까운 시기: {near}Ma (Ma는 백만 년 전)')
        if spec.get('paleo', 'margin') not in PALEO_KINDS: out.append('paleo는 margin(대륙붕 포함 대륙) 또는 coast(당시 해안선)입니다.')
        clash = [key for key in ('year', 'borders', 'rivers', 'past_borders', 'districts') if spec.get(key)] + (['한국 지도'] if view in ('korea', 'south_korea') else [])
        clash += ['현대 나라·시·도 음영' for item in spec.get('shade', []) if _modern_shade(item)][:1]
        if clash: out.append('지질시대 지도에는 현대·역사 자료를 함께 쓸 수 없습니다: ' + ', '.join(clash))
    if spec.get('past_borders') and spec.get('year') is None: out.append('과거 국경(past_borders)은 연도(year)와 함께 씁니다.')
    if spec.get('year') is not None and ma is None:
        modern = (['현대 국경'] if spec.get('borders') else []) + (['시·군·구 경계'] if spec.get('districts') else [])
        modern += ['현대 나라·시·도 음영' for item in spec.get('shade', []) if _modern_shade(item)][:1]
        if modern: out.append('역사 지도(year)에는 현대 자료를 함께 쓰지 않습니다: ' + ', '.join(modern))
    countries, provinces = _load('countries'), _province_names()
    for item in spec.get('shade', []):
        names = item.get('polities', [])
        if names and spec.get('year') is None: out.append('과거 나라(polities) 음영은 연도(year)와 함께 씁니다.')
        elif names and year is not None:
            found = _polities_at(year)
            for name in names:
                if _find_polity(name, year) is None:
                    choices = [en for en in found] + [ko for ko, _ in found.values() if ko]
                    near = difflib.get_close_matches(name, choices, n=3, cutoff=0.4)
                    out.append(f'{_year_text(year)}에 "{name}"이 없습니다.' + (' 비슷한 이름: ' + ', '.join(near) if near else ''))
        for code in item.get('countries', []):
            if code not in countries: out.append(f'나라 코드 {code}를 찾을 수 없습니다. ISO 세 글자 코드를 쓰세요.')
        for name in item.get('provinces', []):
            if name not in provinces: out.append(f'시·도 {name}을 찾을 수 없습니다. 쓸 수 있는 이름: ' + ', '.join(provinces))
        for name in item.get('districts', []):
            if _find_district(name) is None:
                every = list(_load('korea_districts')['districts'])
                same = [key for key in every if key.endswith(' ' + str(name))]
                near = same or difflib.get_close_matches(str(name), every + [key.split(' ', 1)[1] for key in every], n=3, cutoff=0.5)
                out.append(f'시·군·구 "{name}"' + ('은 여러 곳에 있습니다. 시·도를 붙여 쓰세요: ' if same else '을 찾을 수 없습니다.' + (' 비슷한 이름: ' if near else '')) + ', '.join(near))
    for group in ('shade', 'areas'):
        for item in spec.get(group, []):
            if item.get('pattern', 'gray') not in PATTERNS: out.append('음영(pattern)은 ' + ', '.join(PATTERNS) + ' 중 하나입니다.')
    for item in spec.get('areas', []):
        if len(item.get('points', [])) < 3: out.append('영역(areas)의 points는 경위도 세 개 이상이어야 합니다.')
    for item in spec.get('callouts', []):
        if not str(item.get('text') or '').strip(): out.append('말풍선(callouts)에 글(text)이 없습니다.')
        if 'offset' in item and not _is_lonlat(item['offset']): out.append('말풍선의 offset은 [가로, 세로] 화면 거리입니다.')
    for group, key in (('points', 'at'), ('blobs', 'at'), ('callouts', 'at')):
        for item in spec.get(group, []):
            if not _is_lonlat(item.get(key)): out.append(f'{group}의 {key}는 [경도, 위도]여야 합니다.')
    for item in spec.get('routes', []):
        path = item.get('path') or []
        if len(path) < 2 or not all(_is_lonlat(p) for p in path): out.append('경로(routes)의 path는 [경도, 위도] 두 개 이상이어야 합니다.')
    present = [(group, item) for group in MOVABLE for item in spec.get(group, []) if item.get('present')]
    if present and ma is None: out.append('지금 위치(present)는 지질시대(ma) 지도에서만 씁니다.')
    elif present and not out:
        for group, item in present:
            key = MOVABLE[group]
            for lon, lat in [item[key]] if key == 'at' else item[key]:
                try: _past(lon, lat, ma)
                except ValueError as e: out.append(f"{item.get('label') or item.get('text') or group}: {e}")
    if not out:     # 표시한 곳이 지도 밖이면 그려도 보이지 않거나 글씨가 엉뚱한 곳에 붙는다
        spec = _present(spec)
        project = _Projection(VIEWS[view] if isinstance(view, str) else tuple(view))
        for group in ('points', 'blobs', 'callouts'):
            for item in spec.get(group, []):
                x, y = project(*item['at'])
                if not (MARGIN <= x <= W - MARGIN and MARGIN <= y <= H - MARGIN):
                    out.append(f"{item.get('label') or group}의 위치 {item['at']}가 지도 범위 밖입니다. view를 넓혀 주세요.")
    return out


def _modern_shade(item):
    return bool(item.get('countries') or item.get('provinces') or item.get('districts'))


def _is_lonlat(value):
    return isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value)


class _Projection:
    """위도에 맞춰 경도를 줄인 정거 원통 도법. 범위를 캔버스 비율에 맞게 넓혀 틀을 가득 채운다."""
    def __init__(self, box):
        lon0, lat0, lon1, lat1 = box
        self.k = math.cos(math.radians((lat0 + lat1) / 2))
        width, height = (lon1 - lon0) * self.k, lat1 - lat0
        inner_w, inner_h = W - 2 * MARGIN, H - 2 * MARGIN
        self.s = min(inner_w / width, inner_h / height)
        if lon1 - lon0 >= 359:      # 지구 전체는 틀을 가득 채운다. 위아래가 비면 극의 직선과 빈 바다가 남는다.
            self.s = inner_h / height; self.k = inner_w / (lon1 - lon0) / self.s
        self.cx, self.cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2
        self.west, self.wraps = lon0, lon1 > 180     # 태평양 중심 지도는 날짜변경선을 넘는다

    def __call__(self, lon, lat):
        if self.wraps and lon < self.west: lon += 360
        return (W / 2 + (lon - self.cx) * self.k * self.s, H / 2 - (lat - self.cy) * self.s)

    def raw(self, lon, lat):
        return (W / 2 + (lon - self.cx) * self.k * self.s, H / 2 - (lat - self.cy) * self.s)


def _clip(points):
    """Sutherland-Hodgman. 볼록한 틀로 다각형을 자른다."""
    x0, y0, x1, y1 = MARGIN, MARGIN, W - MARGIN, H - MARGIN
    edges = ((lambda p: p[0] >= x0, lambda a, b: _cross_x(a, b, x0)), (lambda p: p[0] <= x1, lambda a, b: _cross_x(a, b, x1)),
             (lambda p: p[1] >= y0, lambda a, b: _cross_y(a, b, y0)), (lambda p: p[1] <= y1, lambda a, b: _cross_y(a, b, y1)))
    for inside, cross in edges:
        if not points: return []
        result, last = [], points[-1]
        for p in points:
            if inside(p):
                if not inside(last): result.append(cross(last, p))
                result.append(p)
            elif inside(last):
                result.append(cross(last, p))
            last = p
        points = result
    return points


def _cross_x(a, b, x):
    t = (x - a[0]) / ((b[0] - a[0]) or 1e-9)
    return (x, a[1] + t * (b[1] - a[1]))


def _cross_y(a, b, y):
    t = (y - a[1]) / ((b[1] - a[1]) or 1e-9)
    return (a[0] + t * (b[0] - a[0]), y)


def _clip_line(points):
    """선을 틀 안의 토막들로 자른다."""
    runs, run = [], []
    box = (MARGIN, MARGIN, W - MARGIN, H - MARGIN)
    for a, b in zip(points, points[1:]):
        seg = _clip_segment(a, b, box)
        if not seg:
            if len(run) > 1: runs.append(run)
            run = []
            continue
        if run and run[-1] == seg[0]:
            run.append(seg[1])
        else:
            if len(run) > 1: runs.append(run)
            run = list(seg)
    if len(run) > 1: runs.append(run)
    return runs


def _clip_segment(a, b, box):
    x0, y0, x1, y1 = box
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0: return None
            continue
        r = q / p
        if p < 0:
            if r > t1: return None
            t0 = max(t0, r)
        else:
            if r < t0: return None
            t1 = min(t1, r)
    return ((a[0] + t0 * dx, a[1] + t0 * dy), (a[0] + t1 * dx, a[1] + t1 * dy))


def _thin(points, tolerance=0.6):
    """화면에서 보이지 않는 꼭짓점을 뺀다. 파일이 작아지고 선이 뭉치지 않는다."""
    if len(points) < 3: return points
    out = [points[0]]
    for p in points[1:-1]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= tolerance: out.append(p)
    out.append(points[-1])
    return out


def _area(points):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))) / 2


def _polygons(rings, project, tolerance=None):
    # 세계 지도처럼 축척이 작으면 더 성기게 줄여도 보이는 모양이 같다. SVG가 상한(1MB)을 넘지 않게 한다.
    tolerance = tolerance or (1.0 if project.s < 4 else 0.6)
    shapes = []
    for ring in rings:
        # 고리를 통째로 옮겨야 날짜변경선 근처에서 선이 화면을 가로지르지 않는다
        for offset in (0, 360) if project.wraps else (0,):
            shape = _clip(_thin([project.raw(p[0] + offset, p[1]) for p in ring], tolerance))
            if len(shape) >= 3 and _area(shape) >= 2: shapes.append(shape)
    return shapes


def _d(shapes, close=True):
    end = 'Z' if close else ''
    return ''.join('M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in shape) + end for shape in shapes)


def _path(shapes, fill='none', stroke='none', width=0.0, dash='', close=None):
    if not shapes: return ''
    extra = f' stroke-dasharray="{dash}"' if dash else ''
    return f'<path d="{_d(shapes, fill != "none" if close is None else close)}" fill="{fill}" fill-rule="evenodd" stroke="{stroke}" stroke-width="{width}"{extra}/>'


def _hatch(shapes, gap=9):
    """대각선 빗금을 다각형 안쪽에만 긋는다. 흑백 인쇄에서 회색과 구분된다."""
    lines = []
    for offset in range(-H, W + H, gap):
        crossing = []
        for shape in shapes:
            for a, b in zip(shape, shape[1:] + shape[:1]):
                fa, fb = a[0] + a[1] - offset, b[0] + b[1] - offset
                if (fa < 0) != (fb < 0):
                    t = fa / (fa - fb)
                    crossing.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        crossing.sort()
        for i in range(0, len(crossing) - 1, 2): lines.append([crossing[i], crossing[i + 1]])
    return _path(lines, stroke=LINE, width=0.8)


def _fill_shapes(shapes, pattern):
    if pattern == 'hatch': return _path(shapes, fill='white', stroke=LINE, width=1) + _hatch(shapes)
    fill = {'gray': '#b5b5b5', 'dark': DARK, 'white': 'white'}[pattern]
    return _path(shapes, fill=fill, stroke=LINE, width=1)


def _center(shapes):
    largest = max(shapes, key=_area)
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(largest, largest[1:] + largest[:1])) or 1e-9
    x = sum((a[0] + b[0]) * (a[0] * b[1] - b[0] * a[1]) for a, b in zip(largest, largest[1:] + largest[:1])) / (3 * area)
    y = sum((a[1] + b[1]) * (a[0] * b[1] - b[0] * a[1]) for a, b in zip(largest, largest[1:] + largest[:1])) / (3 * area)
    return (x, y)


def _plain(text):
    """지도 글씨는 평문이다. $A$, $0^{\\circ}$ 처럼 LaTeX로 적은 것을 글자로 푼다."""
    text = str(text)
    text = re.sub(r'\^\{?\\circ\}?|\\circ|\\degree', '°', text)
    text = re.sub(r'\\(?:mathrm|text)\{([^}]*)\}', r'\1', text)
    return text.replace('$', '').replace('\\,', ' ').strip()


def _label(text, x, y, size=36):
    """글씨 상자의 왼쪽 위 좌표로 바꾼다."""
    text = _plain(text)
    wide = sum(0.55 if ord(c) < 128 else 1 for c in str(text)) * size
    return {'kind': 'korean', 'text': str(text), 'x': round(max(12, min(W - wide - 14, x - wide / 2)), 1), 'y': round(max(12, min(H - size - 16, y - size / 2)), 1), 'size': size, 'rotation': 0}


def _circled(parts, labels):
    """원문자는 시험지 글꼴에 없다. 동그라미는 그림으로 그리고 숫자만 글씨로 얹는다."""
    out = []
    for label in labels:
        number = CIRCLED.get(label['text'])
        if number is None:
            out.append(label); continue
        x, y = label['x'] + label['size'] / 2, label['y'] + label['size'] / 2
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="16" fill="white" stroke="{LINE}" stroke-width="1.6"/>')
        out.append(_label(number, x, y, size=22))
    return out


def _callout(at, item, labels):
    """말풍선: 흰 상자에 꼬리를 붙여 한 선으로 그리고 글은 글씨 레이어에 줄마다 놓는다."""
    x, y = at; size, pad, r, half = 24, 12, 8, 10
    lines = [line for line in str(item['text']).split('\n') if line.strip()] or ['']
    widths = [sum(0.55 if ord(c) < 128 else 1 for c in line) * size for line in lines]
    w, h = max(widths) + 2 * pad, len(lines) * size * 1.3 - size * 0.3 + 2 * pad
    dx, dy = item.get('offset') or [90 if x < W * 0.7 else -90, -70 if y > H * 0.3 else 70]
    cx = min(max(x + dx, MARGIN + w / 2 + 4), W - MARGIN - w / 2 - 4)
    cy = min(max(y + dy, MARGIN + h / 2 + 4), H - MARGIN - h / 2 - 4)
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    vx, vy = x - cx, y - cy
    side = ('right' if vx > 0 else 'left') if abs(vx) * h > abs(vy) * w else ('bottom' if vy > 0 else 'top')
    along = min(max(x if side in ('top', 'bottom') else y, (x0 if side in ('top', 'bottom') else y0) + r + half),
                (x1 if side in ('top', 'bottom') else y1) - r - half)
    inside = x0 < x < x1 and y0 < y < y1     # 점이 상자에 가리면 꼬리를 달지 않는다

    def corner(px, py, start):
        return [(px + r * math.cos(math.radians(start + k * 30)), py + r * math.sin(math.radians(start + k * 30))) for k in range(1, 3)]
    tail = {'top': [(along - half, y0), (x, y), (along + half, y0)], 'right': [(x1, along - half), (x, y), (x1, along + half)],
            'bottom': [(along + half, y1), (x, y), (along - half, y1)], 'left': [(x0, along + half), (x, y), (x0, along - half)]}
    pts = [(x0 + r, y0)] + (tail['top'] if side == 'top' and not inside else []) + [(x1 - r, y0)] + corner(x1 - r, y0 + r, 270)
    pts += [(x1, y0 + r)] + (tail['right'] if side == 'right' and not inside else []) + [(x1, y1 - r)] + corner(x1 - r, y1 - r, 0)
    pts += [(x1 - r, y1)] + (tail['bottom'] if side == 'bottom' and not inside else []) + [(x0 + r, y1)] + corner(x0 + r, y1 - r, 90)
    pts += [(x0, y1 - r)] + (tail['left'] if side == 'left' and not inside else []) + [(x0, y0 + r)] + corner(x0 + r, y0 + r, 180)
    for i, (line, lw) in enumerate(zip(lines, widths)):
        labels.append(_label(line, x0 + pad + lw / 2, y0 + pad + i * size * 1.3 + size / 2, size=size))
    return _path([pts], fill='white', stroke=LINE, width=1.4)


def _km_per_pixel(project):
    return 111.32 / project.s


def _arrow(a, b):
    angle = math.atan2(b[1] - a[1], b[0] - a[0]); size = 15
    left = (b[0] - size * math.cos(angle - 0.42), b[1] - size * math.sin(angle - 0.42))
    right = (b[0] - size * math.cos(angle + 0.42), b[1] - size * math.sin(angle + 0.42))
    return f'<polygon points="{b[0]:.1f},{b[1]:.1f} {left[0]:.1f},{left[1]:.1f} {right[0]:.1f},{right[1]:.1f}" fill="{LINE}" stroke="none"/>'


def render(locked):
    """명세를 (SVG, 글씨 목록)으로 바꾼다."""
    problems = errors(locked)
    if problems: raise ValueError(' / '.join(problems))
    spec = _present(spec_of(locked))
    view = spec['view']
    box = VIEWS[view] if isinstance(view, str) else tuple(view)
    project = _Projection(box)
    # 한국 지도의 시·도 경계는 현대 지도에만 그린다. 시·군·구를 쓰면 다른 범위에서도 남한을 통계청 경계로 그린다.
    korea = spec.get('year') is None and spec.get('ma') is None and (
        (isinstance(view, str) and view in ('korea', 'south_korea')) or bool(spec.get('districts')) or any(item.get('districts') for item in spec.get('shade', [])))
    parts, labels, defs = [f'<rect x="0" y="0" width="{W}" height="{H}" fill="white"/>'], [], []
    land_fill = 'white' if spec.get('land') == 'white' else LAND
    countries, provinces = _load('countries'), _load('korea_provinces')

    # 바탕: 흰 바다와 옅은 육지. 해안선은 가늘고 진하게 긋는다. 육지를 먼저 칠하고 선은 나중에 긋는다.
    # 국경을 그릴 때는 나라 자료를 바탕으로 쓴다. 해상도가 다른 육지 자료와 겹치면 해안선이 두 겹이 된다.
    outlines = []      # (도형, 선 색, 굵기)
    if spec.get('ma') is not None:
        # 지질시대: 당시 대륙 배치. 구멍(내해)까지 한 경로에 넣어 홀짝 채우기로 비운다.
        outlines.append((_polygons(_load('paleo')[spec.get('paleo', 'margin')][str(spec['ma'])], project), LINE, 1.1))
    elif spec.get('borders') or korea:
        for code, country in countries.items():
            if korea and code in ('KOR', 'PRK'): continue
            outlines.append((_polygons(country['rings'], project), LINE, 0.8))
    else:
        outlines.append((_polygons(_load('land'), project), LINE, 1.1))
    if korea:
        for name, province in _load('korea_districts')['provinces'].items():
            if 'merged_into' not in province: outlines.append((_polygons(_korea_rings('provinces', name), project), '#555555', 0.7))
        for name, province in provinces.items():
            if province['country'] == 'PRK': outlines.append((_polygons(province['rings'], project), '#555555', 0.7))
    for shapes, _, _ in outlines: parts.append(_path(shapes, fill=land_fill))      # 나라마다 따로 칠해야 남의 나라 안의 나라가 비지 않는다
    # 바다 가리개에 쓸 육지. 서로 겹치지 않는 고리여야 홀짝 채우기가 맞는다.
    land = [shape for shapes, _, _ in outlines for shape in shapes] if spec.get('ma') is not None or korea else _polygons(_load('land'), project)
    if spec.get('year') is not None:
        # 과거 국경 자료는 해안선이 거칠다. 영역을 칠한 뒤 바다를 흰 면으로 덮어 육지 안쪽만 남긴다.
        year, found = spec['year'], _polities_at(spec['year'])
        if spec.get('past_borders'):
            for name, (_, ids) in found.items():
                if not name.startswith('('):      # 괄호 이름은 여러 나라를 합친 범위라 경계가 겹친다
                    parts.append(_path(_polygons([_history_ring(i) for i in ids], project, 1.5), stroke='#555555', width=0.8, close=True))
        for item in spec.get('shade', []):
            if not item.get('polities'): continue
            rings = [_history_ring(i) for name in item['polities'] for i in found[_find_polity(name, year)][1]]
            shapes = _polygons(rings, project, 1.5)
            if not shapes: raise ValueError('음영으로 칠할 나라가 지도 범위 밖에 있습니다.')
            parts.append(_fill_shapes(shapes, item.get('pattern', 'gray')))
            if item.get('label') and not _modern_shade(item):
                x, y = _center(shapes); labels.append(_label(item['label'], x, y))
        frame = [(MARGIN, MARGIN), (W - MARGIN, MARGIN), (W - MARGIN, H - MARGIN), (MARGIN, H - MARGIN)]
        parts.append(_path([frame] + land, fill='white'))
    if korea and spec.get('districts'):
        # 시·군·구 경계는 맞닿은 선만 한 번씩 저장해 두었다. 시·도 경계와 해안선은 그 위에 덧긋는다.
        data = _load('korea_districts')
        lines = [run for flat in data['lines'] for run in _clip_line(_thin([project(*p) for p in _unpack(flat, data['step'])]))]
        parts.append(_path(lines, stroke='#8c8c8c', width=0.5))
    for shapes, stroke, width in outlines:
        parts.append(_path(shapes, stroke=stroke, width=width, close=True))
    if spec.get('rivers'):
        rivers = [run for line in _load('rivers') for run in _clip_line(_thin([project(*p) for p in line]))]
        parts.append(_path(rivers, stroke=LINE, width=0.8))
    if spec.get('ma') is None:
        parts.append(_path(_polygons(_load('lakes'), project), fill='white', stroke=LINE, width=0.7))

    for item in spec.get('shade', []):
        rings = [ring for code in item.get('countries', []) for ring in countries[code]['rings']]
        rings += [ring for name in item.get('provinces', []) for ring in _province_rings(name)]
        rings += [ring for name in item.get('districts', []) for ring in _korea_rings('districts', _find_district(name))]
        if not rings: continue
        shapes = _polygons(rings, project)
        if not shapes: raise ValueError('음영으로 칠할 곳이 지도 범위 밖에 있습니다.')
        parts.append(_fill_shapes(shapes, item.get('pattern', 'gray')))
        if item.get('label'):
            x, y = _center(shapes); labels.append(_label(item['label'], x, y))
    for item in spec.get('areas', []):
        shapes = _polygons([item['points']], project)
        if not shapes: raise ValueError('영역(areas)이 지도 범위 밖에 있습니다.')
        parts.append(_fill_shapes(shapes, item.get('pattern', 'gray')))
        if item.get('label'):
            x, y = _center(shapes); labels.append(_label(item['label'], x, y))
    for i, item in enumerate(spec.get('blobs', [])):
        # 경계 없이 번지는 음영. 시대별 세력 범위처럼 경계를 확정할 수 없을 때 쓴다.
        x, y = project(*item['at']); rx, ry = item.get('radius', [5, 3])
        grad = f'blob{i}'
        defs.append(f'<radialGradient id="{grad}"><stop offset="0" stop-color="#8c8c8c" stop-opacity="0.75"/><stop offset="0.65" stop-color="#8c8c8c" stop-opacity="0.55"/><stop offset="1" stop-color="#8c8c8c" stop-opacity="0"/></radialGradient>')
        parts.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx * project.k * project.s:.1f}" ry="{ry * project.s:.1f}" fill="url(#{grad})" stroke="none"/>')
        if item.get('label'): labels.append(_label(item['label'], x, y))
    for line in spec.get('lines', []):
        if 'lat' in line:
            ends = [project(box[0] - 400, line['lat']), project(box[2] + 400, line['lat'])]
        else:
            ends = [project(line['lon'], box[1] - 400), project(line['lon'], box[3] + 400)]
        for run in _clip_line(ends):
            parts.append(_path([run], stroke=LINE, width=0.9, dash='7 5'))
            if line.get('label'):
                labels.append(_label(line['label'], run[0][0] + 28, run[0][1] - 16 if 'lat' in line else run[0][1] + 20, size=24))
    for item in spec.get('routes', []):
        points = [project(*p) for p in item['path']]
        runs = _clip_line(points)
        for run in runs: parts.append(_path([run], stroke=LINE, width=2, dash='8 5' if item.get('dash') else ''))
        if runs and item.get('arrow', True): parts.append(_arrow(runs[-1][-2], runs[-1][-1]))
        if item.get('label') and runs:
            mid = runs[0][len(runs[0]) // 2]; labels.append(_label(item['label'], mid[0] + 22, mid[1] - 20))
    for item in spec.get('points', []):
        x, y = project(*item['at'])
        if item.get('open'):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="white" stroke="{LINE}" stroke-width="1.6"/>')
        else:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{LINE}" stroke="none"/>')
        if item.get('label'):
            dx, dy = {'left': (-28, 0), 'up': (0, -30), 'down': (0, 30)}.get(item.get('side'), (28, 0))
            labels.append(_label(item['label'], x + dx, y + dy))   # 점 바로 옆
    for item in spec.get('callouts', []):
        parts.append(_callout(project(*item['at']), item, labels))
    if spec.get('scale_km'):
        # 축척 막대. 한국 지도의 관례다.
        km = spec['scale_km']; length = km / _km_per_pixel(project); x0, y0 = 40, H - 40
        parts.append(f'<path d="M{x0},{y0 - 8}V{y0}H{x0 + length:.1f}V{y0 - 8}" fill="none" stroke="{LINE}" stroke-width="1.6"/>')
        labels.append(_label('0', x0, y0 - 24, size=22)); labels.append(_label(f'{km}km', x0 + length, y0 - 24, size=22))
    labels = _circled(parts, labels)
    parts.append(f'<rect x="{MARGIN}" y="{MARGIN}" width="{W - 2 * MARGIN}" height="{H - 2 * MARGIN}" fill="none" stroke="{LINE}" stroke-width="1.4"/>')
    defs_text = '<defs>' + ''.join(defs) + '</defs>' if defs else ''
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">{defs_text}<g id="geometry">{"".join(parts)}</g></svg>'
    return svg, labels


def options():
    """지도 편집 화면이 고를 수 있는 값."""
    return {'views': VIEWS, 'patterns': PATTERNS, 'provinces': _province_names(), 'districts': list(_load('korea_districts')['districts']), 'ages': paleo_ages(), 'years': YEARS,
            'countries': {code: country['name'] for code, country in _load('countries').items()}}


def preview(locked):
    """지도 편집 화면의 미리보기. 명세에 오류가 있어도 범위만 맞으면 바탕 지도를 보여 주어 교사가 표시를 끌어다 고칠 수 있게 한다."""
    if len(str(locked or '')) > 200000: return {'errors': ['지도 명세가 너무 깁니다.']}
    problems = errors(locked)
    try:
        spec = spec_of(locked)
    except ValueError:
        return {'errors': problems}
    view = spec.get('view')
    if not ((isinstance(view, str) and view in VIEWS) or (isinstance(view, list) and len(view) == 4 and all(isinstance(v, (int, float)) for v in view))):
        return {'errors': problems}
    try:
        svg, labels = render(locked)
    except ValueError as e:
        problems = problems or [str(e)]
        svg = None
        for keys in (('view', 'borders', 'rivers', 'land', 'ma', 'paleo', 'year', 'past_borders'), ('view', 'land')):
            try:
                svg, labels = render(PREFIX + json.dumps({key: spec[key] for key in keys if key in spec}))
                break
            except ValueError:
                continue
        if svg is None: return {'errors': problems}
    project = _Projection(VIEWS[view] if isinstance(view, str) else tuple(view))
    turns = {}
    try: _present(spec, turns)
    except (ValueError, TypeError): turns = {}
    return {'errors': problems, 'svg': svg, 'labels': labels, 'turns': turns,
            'projection': {'k': project.k, 's': project.s, 'cx': project.cx, 'cy': project.cy, 'west': project.west, 'wraps': project.wraps}}


PROMPT = """
지도 자료: 실제 지리 위치가 필요한 그림은 AI가 그리지 않고 앱이 그린다. 해당 그림 자료의 image_mode는 strict, image_creative는 빈 문자열, image_text_* 는 모두 빈 문자열로 두고, image_locked 첫 글자부터 `지도: ` 뒤에 JSON 하나만 쓴다.
- view: world, east_asia, korea, south_korea, japan, china, southeast_asia, south_asia, central_asia, silk_road, middle_east, mediterranean, europe, africa, north_america, south_america, oceania, atlantic, indian_ocean, pacific 중 하나 또는 [서쪽 경도, 남쪽 위도, 동쪽 경도, 북쪽 위도].
- points: [{"at":[경도,위도],"label":"A","side":"right|left|up|down","open":false}] 위치 표시.
- shade: [{"countries":["FRA"],"label":"(가)","pattern":"gray|dark|hatch|white"}] 현대 나라 음영(ISO 세 글자). 한국 지도는 "provinces":["강원특별자치도"], 시·군·구는 "districts":["강원특별자치도 춘천시"](이름이 겹치지 않으면 "춘천시").
- districts: true 남한 시·군·구 경계 표시(통계청 경계). 한국지리의 행정 구역 지도에 쓴다.
- callouts: [{"at":[경도,위도],"text":"(가) 지역","offset":[90,-70]}] 꼬리가 그 위치를 가리키는 말풍선. offset은 화면 거리(가로 1000, 세로 640 기준)이며 생략하면 앱이 정한다. 줄바꿈은 \\n.
- areas: [{"points":[[경도,위도],…],"label":"(가)","pattern":"gray"}] 과거 영토처럼 현대 국경과 다른 범위. 경계가 확실할 때만 쓴다.
- blobs: [{"at":[경도,위도],"radius":[경도폭,위도폭],"label":"(가)"}] 경계를 확정할 수 없는 지역이나 세력 범위의 번지는 음영. 동아시아사의 지역 고르기에 쓴다.
- routes: [{"path":[[경도,위도],…],"label":"❶","dash":false,"arrow":true}] 원정·교역로.
- lines: [{"lat":0,"label":"0°"}] 또는 [{"lon":127}] 점선 위선·경선.
- borders: true 현대 국경 표시(현대 지리만). 역사 지도는 쓰지 않는다. rivers: true 큰 강. scale_km: 100 축척 막대(한국 지도). land: "white" 육지를 희게.
- year: 117 처럼 연도(기원전은 음수, -3400~2024)를 쓰면 그해의 과거 국가 영역 자료(Cliopatria)를 쓸 수 있다. past_borders: true 그해 국경 모두 표시. shade 항목에 "polities":["Roman Empire"] 처럼 그해 나라의 영어 이름(또는 한국어 이름)을 쓰면 그 나라 영역을 칠한다. 연도를 쓰면 borders, countries, provinces는 쓰지 않는다. 고대 한국사·동아시아사처럼 영역 견해가 갈리는 곳은 polities 대신 blobs를 쓴다.
- ma: 250 처럼 지질시대(백만 년 전)를 쓰면 그 시기의 대륙 배치를 바탕으로 그린다(view는 "globe"). 쓸 수 있는 값은 0~535 사이 대체로 5 간격이다(없는 값이면 앱이 가까운 값을 알려 준다). paleo: "margin"(대륙붕 포함 대륙, 기본) 또는 "coast"(당시 해안선). 이때 좌표는 당시의 경위도이며 borders, rivers, year, shade는 쓰지 않는다. 판게아는 ma 250 안팎이다. 지금 위치로 적고 싶으면 points·blobs·routes·areas·callouts 항목에 "present": true를 붙인다. 앱이 판 회전 모형(PALEOMAP)으로 그때 위치를 계산한다(예: 한반도가 그 시기에 있던 곳).
지도 명세의 label·text는 평문이다. LaTeX($A$, \\circ)를 쓰지 않고 A, 0° 처럼 쓴다. 위치 표시는 정답 단서가 되지 않게 A~E나 (가)~(마)로 적고 지명을 쓰지 않는다. 좌표는 알고 있는 사실로만 쓰며, 시대별 범위는 review_note에 교사 확인을 요청한다.
"""
