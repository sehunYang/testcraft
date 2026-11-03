"""시·군·구 경계 자료를 만든다.

원자료: vuski/admdongkor 행정동 경계(통계청 SGIS, 공공누리 제1유형 → CC BY 4.0).
    .runtime/maps/raw/admdongkor/HangJeongDong_ver20261001.geojson

행정동을 시·군·구로 합치고(맞닿은 변을 지움), 이웃과 함께 쓰는 경계는 한 번만 줄여서
이웃끼리 선이 어긋나지 않게 한다. 일반구(수원시 장안구 등)는 시로 합친다.
결과: app/map_data/korea_districts.json.gz

python -I tools/maps/build_korea_districts.py
"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '.runtime/maps/raw/admdongkor/HangJeongDong_ver20261001.geojson'
OUT = ROOT / 'app/map_data/korea_districts.json.gz'
Q = 10 ** 6            # 합칠 때 좌표 단위(백만분의 1도)
STEP = 2000            # 저장 단위(1/2000도, 약 50m)
TOLERANCE = 0.0012     # 줄이기 허용 오차(도). 남한 전도에서 1픽셀이 약 0.009도다.
MIN_AREA = 4e-5        # 이보다 작은 섬(약 0.4km²)은 뺀다
# 2026년 통합 이전 이름으로도 고를 수 있게 한다
LEGACY = {'광주광역시': ('전남광주통합특별시', lambda code: '12210' <= code <= '12330'),
          '전라남도': ('전남광주통합특별시', lambda code: not '12210' <= code <= '12330')}


def signed_area(ring):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1])) / 2


def rings_of(geometry):
    polys = geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]
    for poly in polys:
        for i, ring in enumerate(poly):
            q = []
            for x, y in ring:
                p = (round(x * Q), round(y * Q))
                if not q or q[-1] != p: q.append(p)
            if len(q) > 1 and q[0] == q[-1]: q.pop()
            if len(q) < 3: continue
            # 바깥 고리는 반시계, 구멍은 시계 방향으로 맞춰야 맞닿은 변이 서로 반대 방향이 된다
            if (signed_area(q) > 0) != (i == 0): q.reverse()
            yield q


def dissolve(rings):
    """맞닿은 변(같은 변이 반대 방향으로 두 번)을 지우고 남은 변을 고리로 잇는다."""
    edges = Counter((a, b) for ring in rings for a, b in zip(ring, ring[1:] + ring[:1]))
    out = defaultdict(list)
    for (a, b), n in edges.items():
        if (b, a) not in edges:
            out[a] += [b] * n
    result = []
    while out:
        start = next(iter(out)); ring = [start]; here = start
        while True:
            nxt = out[here].pop()
            if not out[here]: del out[here]
            if nxt == start: break
            ring.append(nxt); here = nxt
            if here not in out: break        # 끊긴 변(원자료 오류)은 여기까지만 잇는다
        if len(ring) >= 3: result.append(ring)
    return result


def douglas(points, tol):
    if len(points) < 3: return points
    keep = [False] * len(points); keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        (x0, y0), (x1, y1) = points[i], points[j]
        dx, dy = x1 - x0, y1 - y0; norm = (dx * dx + dy * dy) ** 0.5
        best, at = -1, None
        for k in range(i + 1, j):
            x, y = points[k]
            d = abs(dy * (x - x0) - dx * (y - y0)) / norm if norm else ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5
            if d > best: best, at = d, k
        if at is not None and best > tol:
            keep[at] = True; stack += [(i, at), (at, j)]
    return [p for p, k in zip(points, keep) if k]


def simplify_shared(groups):
    """이웃이 바뀌는 점에서 경계를 토막 내고 토막마다 한 번만 줄인다. 같은 토막은 이웃도 같은 결과를 쓴다."""
    owner = {(a, b): key for key, rings in groups.items() for ring in rings for a, b in zip(ring, ring[1:] + ring[:1])}
    cache = {}
    tol = TOLERANCE * Q

    def arc(points):
        forward, backward = tuple(points), tuple(reversed(points))
        key = min(forward, backward)
        if key not in cache: cache[key] = douglas(list(key), tol)
        done = cache[key]
        return done if key == forward else done[::-1]

    out = {}
    for key, rings in groups.items():
        kept = []
        for ring in rings:
            n = len(ring)
            nb = [owner.get((ring[(i + 1) % n], ring[i])) for i in range(n)]       # i번째 변 건너편
            breaks = [i for i in range(n) if nb[i - 1] != nb[i]]
            if not breaks:
                start = ring.index(min(ring)); rot = ring[start:] + ring[:start]
                other = [rot[0]] + rot[1:][::-1]
                canon = min(rot, other)
                done = douglas(canon + [canon[0]], tol)[:-1]
                simple = done if canon == rot else [done[0]] + done[1:][::-1]
            else:
                simple = []
                for s, e in zip(breaks, breaks[1:] + [breaks[0] + n]):
                    piece = [ring[i % n] for i in range(s, e + 1)]
                    simple += arc(piece)[:-1]
            if len(simple) >= 3: kept.append(simple)
        out[key] = kept
    return out


def encode(ring):
    pts = [(round(x * STEP / Q), round(y * STEP / Q)) for x, y in ring]
    dedup = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    if len(dedup) > 1 and dedup[0] == dedup[-1]: dedup.pop()
    if len(dedup) < 3 or abs(signed_area(dedup)) / STEP / STEP < MIN_AREA: return None
    flat = [dedup[0][0], dedup[0][1]]
    for a, b in zip(dedup, dedup[1:]): flat += [b[0] - a[0], b[1] - a[1]]
    return flat


def decode(flat):
    x, y = flat[0], flat[1]; out = [(x, y)]
    for i in range(2, len(flat), 2):
        x += flat[i]; y += flat[i + 1]; out.append((x, y))
    return out


def inner_lines(districts):
    """같은 시·도 안에서 두 시·군·구가 맞닿은 경계를 한 번씩만 선으로 남긴다. 해안선과 시·도 경계는 시·도 고리가 긋는다."""
    owner = {}
    for key, d in districts.items():
        for ring in map(decode, d['rings']):
            for a, b in zip(ring, ring[1:] + ring[:1]): owner[(a, b)] = d['sido']
    edges = {(a, b) for (a, b), sido in owner.items() if a < b and owner.get((b, a)) == sido}
    near = defaultdict(set)
    for a, b in edges: near[a].add(b); near[b].add(a)
    lines = []
    def walk(start, nxt):
        line = [start]
        here = start
        while True:
            near[here].discard(nxt); near[nxt].discard(here)
            line.append(nxt); here = nxt
            if len(near[here]) != 1: return line       # 갈림길이나 끝에서 멈춘다
            nxt = next(iter(near[here]))
    for start in [p for p in near if len(near[p]) != 2]:
        while near[start]: lines.append(walk(start, next(iter(near[start]))))
    for start in list(near):        # 남은 것은 갈림길 없는 고리(다른 구에 둘러싸인 구)
        while near[start]: lines.append(walk(start, next(iter(near[start]))))
    out = []
    for line in lines:
        flat = [line[0][0], line[0][1]]
        for a, b in zip(line, line[1:]): flat += [b[0] - a[0], b[1] - a[1]]
        out.append(flat)
    return out


def main():
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    dongs, meta = defaultdict(list), {}
    for f in data['features']:
        p = f['properties']; sido, name = p['sidonm'], p['sggnm']
        city = re.fullmatch(r'(.+?시)(.+구)', name)
        if city and not sido.endswith(('특별시', '광역시')): name = city.group(1)      # 일반구는 시로 합친다
        key = f'{sido} {name}'
        dongs[key] += list(rings_of(f['geometry']))
        meta.setdefault(key, {'sido': sido, 'name': name, 'code': p['sgg'][:4] + '0' if city else p['sgg']})
    merged = {key: dissolve(rings) for key, rings in dongs.items()}
    simple = simplify_shared(merged)
    districts = {}
    for key, rings in sorted(simple.items()):
        encoded = [r for r in (encode(ring) for ring in rings) if r]
        if encoded: districts[key] = {**meta[key], 'rings': encoded}
    # 시·도는 줄인 시·군·구를 다시 합친다. 저장 단위로 맞춘 좌표라 맞닿은 변이 정확히 겹친다.
    by_sido = defaultdict(list)
    for key, d in districts.items():
        by_sido[d['sido']] += [decode(r) for r in d['rings']]
        for old, (sido, member) in LEGACY.items():
            if d['sido'] == sido and member(d['code']): by_sido[old] += [decode(r) for r in d['rings']]
    lines = inner_lines(districts)
    provinces = {}
    for sido, rings in by_sido.items():
        flat = []
        for ring in dissolve(rings):
            f = [ring[0][0], ring[0][1]]
            for a, b in zip(ring, ring[1:]): f += [b[0] - a[0], b[1] - a[1]]
            if abs(signed_area(ring)) / STEP / STEP >= MIN_AREA: flat.append(f)
        provinces[sido] = {'rings': flat, **({'merged_into': LEGACY[sido][0]} if sido in LEGACY else {})}
    out = {'source': 'vuski/admdongkor HangJeongDong_ver20261001 (통계청 SGIS 행정동 경계, 공공누리 제1유형 · CC BY 4.0)',
           'step': STEP, 'districts': districts, 'provinces': provinces, 'lines': lines}
    raw = json.dumps(out, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    OUT.write_bytes(gzip.compress(raw, 9))
    points = sum(len(r) // 2 for d in districts.values() for r in d['rings'])
    print(f'시·군·구 {len(districts)}개, 시·도 {len(provinces)}개, 꼭짓점 {points}, {len(raw) / 1e6:.2f}MB → {OUT.stat().st_size / 1e6:.2f}MB')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
