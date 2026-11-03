# -*- coding: utf-8 -*-
"""과거 지도 자료를 만든다. 앱에는 줄인 결과만 들어간다.

    python -I tools/maps/build_past_map_data.py

- 역사 국경: Cliopatria v0.2.1 (Seshat, CC BY 4.0). 한국어 이름은 history_names_ko.json(교과서 표기 기준으로 정리한 표)을 먼저 쓰고,
  표에 없으면 위키백과 한국어 문서 제목, Wikidata(CC0)의 ko 표제어 순으로 쓴다.
- 지질시대 해안선: PaleoMAP PaleoCoastlines v7.2 (Kocsis·Scotese, CC BY 4.0).

원본: .runtime/maps/raw/cliopatria/, .runtime/maps/raw/paleomap/   결과: app/map_data/history.json.gz, paleo.json.gz
"""
import collections
import gzip
import json
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_map_data import simplify  # noqa: E402

RAW = ROOT / '.runtime/maps/raw'
OUT = ROOT / 'app/map_data'
STEP = 20       # 역사 국경 좌표 단위 1/20도(약 5 km). 원자료 꼭짓점 간격이 0.3도 안팎이라 잃는 것이 없다.
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)


def write(name, value):
    path = OUT / name
    path.write_bytes(gzip.compress(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), 9, mtime=0))
    print(name, path.stat().st_size // 1024, 'KB')


# 현대 한국 교과서 표기 기준으로 정리한 이름표. {영어 이름: [한국어 이름, t(교과서) | x(외래어 표기법으로 옮김)]}
# 기준은 history_names_ko.md 에 있다. 괄호로 싼 묶음 영역은 속한 이름만 옮겨 두고 "전체"는 아래에서 붙인다.
NAMES_KO = {en: ko for en, (ko, _) in json.loads((Path(__file__).resolve().parent / 'history_names_ko.json').read_text(encoding='utf-8')).items()}
# 이름표가 생기기 전에 손으로 고친 이름. 이름표에 없는 나라에만 쓰인다.
OVERRIDES = {
    'Joseon': '조선', 'Gojoseon': '고조선', 'Republic of Korea': '대한민국', "Democratic People's Republic of Korea": '조선민주주의인민공화국',
    'Roman Empire': '로마 제국', 'Eastern Roman Empire': '비잔티움 제국', 'Western Roman Empire': '서로마 제국', 'Roman Republic': '로마 공화정',
    'Han Dynasty': '한', 'Qin Dynasty': '진(秦)', 'Jin': '진(晉)', 'Former Jin': '서진', 'Sui Dynasty': '수', 'Tang Dynasty': '당', 'Song': '송',
    'Northern Song': '북송', 'Southern Song': '남송', 'Yuan Dynasty': '원', 'Great Yuan': '원', 'Great Mongol State': '몽골 제국', 'Ming Dynasty': '명',
    'Qing Dynasty': '청', 'Republic of China': '중화민국', "People's Republic of China": '중화인민공화국', 'Xiongnu': '흉노', 'Southern Xiongnu': '남흉노',
    'Empire of Japan': '일본 제국', 'Japan': '일본', 'Abbasid Caliphate': '아바스 왕조', 'Buyid Dynasty': '부와이 왕조', 'Sasanian Empire': '사산 왕조 페르시아',
    'Kingdom of France': '프랑스 왕국', 'Bourbon Kingdom of France': '부르봉 왕정 프랑스', 'Carolingian Empire': '카롤루스 왕조 프랑크 왕국',
    'Merovingian Empire': '메로베우스 왕조 프랑크 왕국', 'Kingdom of the Franks': '프랑크 왕국', 'Kushan Empire': '쿠샨 왕조',
    'Mughal Empire': '무굴 제국', 'Ottoman Empire': '오스만 제국', 'Great Mongol Empire': '몽골 제국', 'Hungary': '헝가리', 'Syria': '시리아', 'Assyria': '아시리아',
}
AGENT = {'User-Agent': 'TestCraft-map-data/1.0 (education; https://github.com/sehunYang/testcraft)'}


def ask(url, params):
    request = urllib.request.Request(url + '?' + urllib.parse.urlencode(params), headers=AGENT)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=60) as res: return json.loads(res.read())
        except urllib.error.HTTPError as e:      # 너무 자주 물으면 429로 막힌다. 알려 준 만큼 기다린다.
            if e.code != 429 or attempt == 5: raise
            time.sleep(int(e.headers.get('Retry-After') or 10 * (attempt + 1)))


def cached(name, keys, fetch):
    """한 번 받은 것은 저장해 두고 다시 받지 않는다."""
    path = RAW / f'cliopatria/{name}.json'
    cache = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    missing = sorted(set(keys) - set(cache))
    for i in range(0, len(missing), 50):
        cache.update(fetch(missing[i:i + 50]))
        for key in missing[i:i + 50]: cache.setdefault(key, '')
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding='utf-8')
        print(name, min(i + 50, len(missing)), '/', len(missing)); time.sleep(2)
    return cache


def wikidata_ko(ids):
    data = ask('https://www.wikidata.org/w/api.php', {'action': 'wbgetentities', 'ids': '|'.join(ids), 'props': 'labels', 'languages': 'ko', 'format': 'json'})
    return {qid: e.get('labels', {}).get('ko', {}).get('value', '') for qid, e in data.get('entities', {}).items()}


def wikipedia_ko(titles):
    """영어 위키백과 문서에 연결된 한국어 문서 제목. 나라마다 문서가 따로라서 Wikidata보다 정확하다."""
    data = ask('https://en.wikipedia.org/w/api.php', {'action': 'query', 'titles': '|'.join(titles), 'prop': 'langlinks', 'lllang': 'ko', 'redirects': 1, 'format': 'json', 'formatversion': 2})
    query = data.get('query', {})
    back = {}
    for step in query.get('normalized', []) + query.get('redirects', []): back.setdefault(step['to'], []).append(step['from'])
    out = {}
    for page in query.get('pages', []):
        ko = (page.get('langlinks') or [{}])[0].get('title', '')
        sources, frontier = {page['title']}, [page['title']]
        while frontier:
            for origin in back.get(frontier.pop(), []):
                if origin not in sources: sources.add(origin); frontier.append(origin)
        for title in sources: out[title] = ko
    return out


def korean_names(features):
    pages, qids = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for f in features:
        p = f['properties']
        if p.get('Wikipedia'): pages[p['Name']][p['Wikipedia'].replace('_', ' ')] += 1
        if p.get('Wikidata'): qids[p['Name']][p['Wikidata']] += 1
    page = {name: c.most_common(1)[0][0] for name, c in pages.items()}
    qid = {name: c.most_common(1)[0][0] for name, c in qids.items()}
    by_page, by_qid = cached('wikipedia_ko', page.values(), wikipedia_ko), cached('wikidata_ko', qid.values(), wikidata_ko)
    # 여러 나라가 같은 문서·항목을 가리키면 그 이름은 어느 나라 것인지 알 수 없으므로 쓰지 않는다
    plain = [n for n in {f['properties']['Name'] for f in features} if not n.startswith('(')]
    shared_page = {k for k, v in collections.Counter(page.get(n) for n in plain).items() if v > 1}
    shared_qid = {k for k, v in collections.Counter(qid.get(n) for n in plain).items() if v > 1}

    def one(name):
        if name in NAMES_KO: return NAMES_KO[name]
        if name in OVERRIDES: return OVERRIDES[name]
        if page.get(name) and page[name] not in shared_page and by_page.get(page[name]): return by_page[page[name]]
        if qid.get(name) and qid[name] not in shared_qid and by_qid.get(qid[name]): return by_qid[qid[name]]
        return ''
    out = {}
    for name in {f['properties']['Name'] for f in features}:
        if name.startswith('('):      # 묶음 영역. 속한 나라를 모두 합친 범위다.
            inner = NAMES_KO.get(name) or one(name[1:-1]) or by_page.get(page.get(name, ''), '') or by_qid.get(qid.get(name, ''), '')
            out[name] = inner + ' 전체' if inner else ''
        else:
            out[name] = one(name)
    return out, qid


def history():
    source = RAW / 'cliopatria/x/cliopatria_polities_only_v021.geojson'
    if not source.exists():
        zipfile.ZipFile(RAW / 'cliopatria/cliopatria.geojson.zip').extractall(source.parent)
    features = [f for f in json.loads(source.read_text(encoding='utf-8'))['features'] if f['properties']['Type'] == 'POLITY']
    korean, qids = korean_names(features)
    names, name_index, rings, ring_index, rows = [], {}, [], {}, []
    for f in sorted(features, key=lambda f: (f['properties']['Name'], f['properties']['FromYear'])):
        p, g = f['properties'], f['geometry']
        polygons = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
        ids = []
        for polygon in polygons:
            for ring in polygon:      # 바깥 고리와 구멍을 함께 둔다. 홀짝 채우기로 구멍이 비워진다.
                q = []
                for x, y in ring:
                    point = (round(x * STEP), round(y * STEP))
                    if not q or q[-1] != point: q.append(point)
                if len(q) > 1 and q[0] == q[-1]: q.pop()
                if len(q) < 3: continue
                key = tuple(q)
                if key not in ring_index:
                    ring_index[key] = len(rings)
                    flat = [q[0][0], q[0][1]]
                    for a, b in zip(q, q[1:]): flat += [b[0] - a[0], b[1] - a[1]]
                    rings.append(flat)
                ids.append(ring_index[key])
        if not ids: continue
        name = p['Name']
        if name not in name_index:
            name_index[name] = len(names)
            names.append([name, korean.get(name, ''), qids.get(name, '')])
        i = name_index[name]
        last = rows[-1] if rows else None
        # 다음 시기와 모양이 같으면 한 줄로 합친다
        if last and last[0] == i and last[3] == ids and last[2] + 1 >= p['FromYear']: last[2] = p['ToYear']
        else: rows.append([i, p['FromYear'], p['ToYear'], ids])
    write('history.json.gz', {'source': 'Cliopatria v0.2.1 (Seshat Global History Databank), CC BY 4.0; 한국어 이름은 교과서 표기 기준 이름표(일부 Wikidata CC0)',
                              'step': STEP, 'names': names, 'rings': rings, 'rows': rows})
    print('나라', len(names), '시기', len(rows), '고리', len(rings), '한국어 이름 없음', sum(not n[1] for n in names))


def shapefile_rings(data):
    """ESRI 다각형(종류 5)만 읽는다. 좌표는 경위도다."""
    pos, out = 100, []
    while pos < len(data):
        _, length = struct.unpack('>ii', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length * 2]; pos += 8 + length * 2
        if struct.unpack('<i', body[:4])[0] != 5: continue
        parts, points = struct.unpack('<ii', body[36:44])
        starts = list(struct.unpack(f'<{parts}i', body[44:44 + 4 * parts])) + [points]
        xy = struct.unpack(f'<{2 * points}d', body[44 + 4 * parts:44 + 4 * parts + 16 * points])
        pts = list(zip(xy[0::2], xy[1::2]))
        out += [pts[a:b] for a, b in zip(starts, starts[1:])]
    return out


def paleo():
    archive = zipfile.ZipFile(RAW / 'paleomap/paleocoastlines_v7_shapefiles.zip')
    shapes = {'coast': {}, 'margin': {}}
    for name in archive.namelist():
        folder, _, file = name.partition('/')
        if folder not in ('CS', 'CM') or not file.endswith('.shp'): continue
        age = int(file.split('Ma')[0])
        out = []
        for ring in shapefile_rings(archive.read(name)):
            thin = simplify(ring, 0.1)
            if len(thin) >= 4: out.append([[round(x, 1), round(y, 1)] for x, y in thin])
        shapes['coast' if folder == 'CS' else 'margin'][str(age)] = out
    ages = sorted(int(a) for a in shapes['coast'])
    write('paleo.json.gz', {'source': 'PaleoMAP PaleoCoastlines v7.2 (Kocsis & Scotese 2021), CC BY 4.0', 'ages': ages, **shapes})


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    if not (OUT / "paleo.json.gz").exists(): paleo()
    history()
