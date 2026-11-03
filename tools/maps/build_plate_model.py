"""판 회전 자료를 만든다. 지금 위치를 지질시대의 위치로 옮길 때 쓴다.

원자료: PaleoMAP PaleoCoastlines 레코드(Kocsis & Scotese, Zenodo 7994000, CC BY 4.0)의
    paleomap_global_plate_model_v19o_r1c.zip → .runtime/maps/raw/paleomap_rot/x/
    m06c9h_3id_forPgeog_19o_r1c.rot (판 회전), PALEOMAP_PlatePolygons__forPgeog_v19o.gpml (판 다각형)
지질시대 해안선(paleo.json.gz)과 같은 판 모형이다.
결과: app/map_data/plates.json.gz

python -I tools/maps/build_plate_model.py
"""
import gzip
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / '.runtime/maps/raw/paleomap_rot/x'
OUT = ROOT / 'app/map_data/plates.json.gz'
STEP = 100              # 판 다각형 저장 단위(0.01도)
TOLERANCE = 0.03        # 판 다각형 줄이기 허용 오차(도)
NS = {'gml': 'http://www.opengis.net/gml', 'gpml': 'http://www.gplates.org/gplates'}


def rotations():
    """같은 (움직이는 판, 기준 판)이 이어지는 줄을 한 묶음으로 둔다. 999로 시작하는 줄은 원자료에서 끈 것이다."""
    seqs = []
    for line in (RAW / 'm06c9h_3id_forPgeog_19o_r1c.rot').read_text(encoding='latin-1').splitlines():
        head = line.split('!')[0].split()
        if len(head) < 6: continue
        moving, age, lat, lon, angle, fixed = int(head[0]), *map(float, head[1:5]), int(head[5])
        if moving == 999: continue        # 미래(음수) 줄도 0Ma 앞뒤를 잇는 보간에 필요하다
        if seqs and seqs[-1][0] == moving and seqs[-1][1] == fixed and age >= seqs[-1][2][-1][0]:
            seqs[-1][2].append([age, lat, lon, angle])
        else:
            seqs.append([moving, fixed, [[age, lat, lon, angle]]])
    return [s for s in seqs if len(s[2]) > 1]


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


def polygons():
    root = ET.parse(RAW / 'PALEOMAP_PlatePolygons__forPgeog_v19o.gpml').getroot()
    out = []
    for member in root.findall('gml:featureMember', NS):
        feature = member[0]
        plate = feature.find('gpml:reconstructionPlateId/gpml:ConstantValue/gpml:value', NS)
        if plate is None: continue
        times = [t.text for t in feature.findall('gml:validTime/gml:TimePeriod/*/gml:TimeInstant/gml:timePosition', NS)]
        # 쓸 수 있는 기간: begin(오래된 쪽)~end(최근 쪽). 먼 과거·먼 미래와 0~0(기간 미지정)은 비워 둔다.
        begin, end = (float(t) if t and t.replace('.', '', 1).isdigit() else None for t in (times + [None, None])[:2])
        if begin == end == 0: begin = end = None
        for pos in feature.iter('{http://www.opengis.net/gml}posList'):
            nums = list(map(float, pos.text.split()))
            ring = [(nums[i + 1], nums[i]) for i in range(0, len(nums) - 1, 2)]      # 원자료는 위도, 경도 순서다
            ring = douglas(ring, TOLERANCE)
            q = []
            for x, y in ring:
                p = (round(x * STEP), round(y * STEP))
                if not q or q[-1] != p: q.append(p)
            if len(q) > 1 and q[0] == q[-1]: q.pop()
            if len(q) < 3: continue
            flat = [q[0][0], q[0][1]]
            for a, b in zip(q, q[1:]): flat += [b[0] - a[0], b[1] - a[1]]
            out.append([int(plate.text), begin, end, flat])
    return out


def main():
    rots, polys = rotations(), polygons()
    data = {'source': 'PALEOMAP Global Plate Model v19o_r1c (Scotese; Kocsis & Scotese 2021 PaleoCoastlines 레코드, CC BY 4.0)',
            'step': STEP, 'rotations': rots, 'polygons': polys}
    raw = json.dumps(data, separators=(',', ':')).encode('utf-8')
    OUT.write_bytes(gzip.compress(raw, 9))
    begins = sorted({p[1] for p in polys if p[1] is not None})
    print(f'회전 묶음 {len(rots)}개, 판 {len({r[0] for r in rots})}개, 다각형 {len(polys)}개, 시작 시기 {begins[:5]}…{begins[-5:]}, {len(raw) / 1e6:.2f}MB → {OUT.stat().st_size / 1e6:.2f}MB')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
