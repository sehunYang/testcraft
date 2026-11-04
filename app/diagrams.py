"""생명과학·화학 도식. 정확해야 하는 그림을 AI가 그리지 않고 앱이 명세대로 그린다(지도와 같은 방식).

그림 규칙(image_locked)이 "도식: {JSON}" 으로 시작하면 이 모듈이 흑백 선화 SVG와 글씨 목록을 만든다.
글씨(번호, 기호, 원소 기호, 이름표)는 글씨 레이어로 따로 둔다.

종류(type): pedigree 가계도 · foodweb 먹이 그물 · pyramid 생태 피라미드 · sequence 염기 서열 · cell 세포 소기관 ·
particles 반응 입자 모형 · energy 반응 경로-에너지
물리(diagrams_physics): mechanics 역학 상황 · circuit 회로 · graph 그래프 · panels 여러 칸
"""
import json
import math

from .maps import _label

PREFIX = '도식:'
W, H = 1000, 640
LINE, GRAY, DARK = '#111111', '#9a9a9a', '#555555'
TYPES = ('pedigree', 'foodweb', 'pyramid', 'sequence', 'cell', 'particles', 'energy', 'mechanics', 'circuit', 'graph', 'panels')
ORGANELLES = {'nucleus': '핵', 'mitochondria': '미토콘드리아', 'chloroplast': '엽록체', 'golgi': '골지체', 'er': '소포체',
              'ribosome': '리보솜', 'lysosome': '리소좀', 'vacuole': '액포', 'cellwall': '세포벽', 'membrane': '세포막', 'centriole': '중심체'}
BASES = set('ATGCU')


def is_diagram(locked):
    return str(locked or '').strip().startswith(PREFIX)


def spec_of(locked):
    text = str(locked or '').strip()
    if not text.startswith(PREFIX): raise ValueError('도식 명세가 아닙니다.')
    try:
        spec = json.loads(text[len(PREFIX):])
    except ValueError as e:
        raise ValueError(f'도식 명세의 JSON 오류: {e}') from None
    if not isinstance(spec, dict): raise ValueError('도식 명세는 JSON 객체여야 합니다.')
    return spec


def errors(locked):
    try:
        spec = spec_of(locked)
    except ValueError as e:
        return [str(e)]
    kind = spec.get('type')
    if kind not in TYPES: return ['도식 종류(type)는 ' + ', '.join(TYPES) + ' 중 하나입니다.']
    out = CHECK[kind](spec)
    if not out:
        try: RENDER[kind](spec, [], [])
        except (ValueError, KeyError, TypeError, ZeroDivisionError, IndexError) as e: out.append(f'도식을 그릴 수 없습니다: {e}')
    return out


def render(locked):
    problems = errors(locked)
    if problems: raise ValueError(' / '.join(problems))
    spec = spec_of(locked)
    parts, labels = [f'<rect x="0" y="0" width="{W}" height="{H}" fill="white"/>'], []
    RENDER[spec['type']](spec, parts, labels)
    if spec['type'] not in _phys.RENDER: labels = [_grow(x) for x in labels]      # 물리 도식은 자리를 잡을 때 이미 키웠다
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}"><g id="geometry">{"".join(parts)}</g></svg>', labels


# ---------------------------------------------------------------- 공통 그리기
TEXT_SCALE = 1.25     # 시험지에 들어가면 그림 글씨가 본문보다 너무 작다. 가운데를 지키며 키운다(2026-11-04).


def _grow(label, k=TEXT_SCALE):
    from .diagrams_physics import _width
    old = label['size']; new = round(old * k)
    wide = (lambda s: _width(label['text'], s)) if label.get('kind') == 'physics' else (lambda s: _text_width(label['text'], s))
    x = label['x'] - (wide(new) - wide(old)) / 2; y = label['y'] - (new - old) / 2
    return {**label, 'size': new, 'x': round(max(6, min(W - wide(new) - 6, x)), 1), 'y': round(max(6, min(H - new - 6, y)), 1)}


def _p(d, fill='none', stroke=LINE, width=2.5, dash=''):
    extra = f' stroke-dasharray="{dash}"' if dash else ''
    return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"{extra}/>'


def _line(a, b, width=2.5, dash=''):
    return _p(f'M{a[0]:.1f},{a[1]:.1f}L{b[0]:.1f},{b[1]:.1f}', width=width, dash=dash)


def _arrow(a, b, width=2.5, head=14):
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    tip = b
    base = (b[0] - head * math.cos(ang), b[1] - head * math.sin(ang))
    left = (base[0] + head * .45 * math.sin(ang), base[1] - head * .45 * math.cos(ang))
    right = (base[0] - head * .45 * math.sin(ang), base[1] + head * .45 * math.cos(ang))
    return _line(a, base, width) + f'<polygon points="{tip[0]:.1f},{tip[1]:.1f} {left[0]:.1f},{left[1]:.1f} {right[0]:.1f},{right[1]:.1f}" fill="{LINE}" stroke="none"/>'


def _double_arrow(a, b, width=2):
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return _arrow(mid, a, width, 11) + _arrow(mid, b, width, 11)


def _circle(c, r, fill='white', width=2.5):
    return f'<circle cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="{r:.1f}" fill="{fill}" stroke="{LINE}" stroke-width="{width}"/>'


def _text_width(text, size):
    return sum(.55 if ord(ch) < 128 else 1 for ch in str(text)) * size


def _need(spec, key, kind=list):
    value = spec.get(key)
    return isinstance(value, kind) and bool(value)


# ---------------------------------------------------------------- 가계도
TRAIT_FILL = {'': 'white', 'a': LINE, 'b': GRAY}


def _check_pedigree(spec):
    out = []
    if not _need(spec, 'generations'): return ['가계도는 generations(세대별 구성원 번호 목록)가 필요합니다.']
    people = {str(p.get('id')): p for p in spec.get('people', [])}
    ids = [str(i) for row in spec['generations'] for i in row]
    if len(ids) != len(set(ids)): out.append('한 구성원이 두 세대에 들어 있습니다.')
    for i in ids:
        p = people.get(i)
        if not p: out.append(f'구성원 {i}의 정보(people)가 없습니다.'); continue
        if p.get('sex') not in ('M', 'F'): out.append(f'구성원 {i}의 sex는 M(남자) 또는 F(여자)입니다.')
        if p.get('trait', '') not in ('', 'a', 'b', 'ab'): out.append(f'구성원 {i}의 trait는 "", "a", "b", "ab" 중 하나입니다.')
    for pair in spec.get('couples', []):
        if len(pair) != 2 or any(str(x) not in ids for x in pair): out.append(f'부부 {pair}의 번호를 확인해 주세요.')
    for fam in spec.get('children', []):
        if not all(str(x) in ids for x in fam.get('parents', []) + fam.get('kids', [])): out.append(f'자녀 관계 {fam}의 번호를 확인해 주세요.')
    if max(len(r) for r in spec['generations']) > 10: out.append('한 세대는 10명까지 그릴 수 있습니다.')
    return out


def _person(c, sex, trait, carrier, s=46):
    x, y = c; h = s / 2; parts = []
    def shape(fill):
        return (f'<rect x="{x - h:.1f}" y="{y - h:.1f}" width="{s}" height="{s}" fill="{fill}" stroke="{LINE}" stroke-width="2.5"/>' if sex == 'M'
                else _circle(c, h, fill))
    if trait == 'ab':      # 두 형질이 함께: 왼쪽 반 검정, 오른쪽 반 회색
        parts.append(shape(GRAY))
        if sex == 'M': parts.append(f'<rect x="{x - h:.1f}" y="{y - h:.1f}" width="{h:.1f}" height="{s}" fill="{LINE}" stroke="none"/>')
        else: parts.append(f'<path d="M{x:.1f},{y - h:.1f}A{h:.1f},{h:.1f} 0 0 0 {x:.1f},{y + h:.1f}Z" fill="{LINE}" stroke="none"/>')
        parts.append(shape('none'))
    else:
        parts.append(shape(TRAIT_FILL[trait]))
    if carrier: parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{LINE if trait in ("", "b") else "white"}" stroke="none"/>')
    return ''.join(parts)


def _pedigree(spec, parts, labels):
    people = {str(p['id']): p for p in spec['people']}
    rows = [[str(i) for i in row] for row in spec['generations']]
    legend = spec.get('legend', True)
    right = 720 if legend else 960
    gap = min(150, (H - 120) / max(1, len(rows) - 1)) if len(rows) > 1 else 0
    top = (H - gap * (len(rows) - 1)) / 2 - 10
    pos = {}
    for g, row in enumerate(rows):
        step = min(110, (right - 60) / max(1, len(row)))
        x0 = 40 + (right - 40) / 2 - step * (len(row) - 1) / 2
        for k, i in enumerate(row): pos[i] = (x0 + k * step, top + g * gap)
    s, h = 46, 23
    for a, b in spec.get('couples', []):
        a, b = sorted((str(a), str(b)), key=lambda i: pos[i][0])
        parts.append(_line((pos[a][0] + h, pos[a][1]), (pos[b][0] - h, pos[b][1])))
    for fam in spec.get('children', []):
        par = [str(x) for x in fam.get('parents', [])]; kids = [str(x) for x in fam['kids']]
        if len(par) == 2: top_pt = ((pos[par[0]][0] + pos[par[1]][0]) / 2, pos[par[0]][1])
        else: top_pt = (pos[par[0]][0], pos[par[0]][1] + h)
        bar = pos[kids[0]][1] - h - 26
        xs = [pos[k][0] for k in kids] + [top_pt[0]]
        parts.append(_line(top_pt, (top_pt[0], bar)))
        parts.append(_line((min(xs), bar), (max(xs), bar)))
        for k in kids: parts.append(_line((pos[k][0], bar), (pos[k][0], pos[k][1] - h)))
    used = set()
    for i, c in pos.items():
        p = people[i]; trait = p.get('trait', '')
        used.add((p['sex'], trait))
        parts.append(_person(c, p['sex'], trait, p.get('carrier')))
        labels.append(_label(p.get('label', i), c[0], c[1] + h + 18, size=24))
    if legend:
        names = spec.get('traits', {'a': '형질 ㉠ 발현', 'b': '형질 ㉡ 발현', 'ab': '㉠, ㉡ 발현'})
        entries = [(sex, '') for sex in ('M', 'F')] + sorted({u for u in used if u[1]}, key=lambda u: ('a', 'b', 'ab').index(u[1]) * 2 + (u[0] == 'F'))
        y = max(70, H / 2 - len(entries) * 23)
        for sex, trait in entries:
            parts.append(_person((775, y), sex, trait, False, s=30))
            who = '남자' if sex == 'M' else '여자'
            text = f"정상 {who}" if not trait else f"{names.get(trait, trait)} {who}"
            labels.append({**_label(text, 0, 0, size=22), 'x': 800.0, 'y': round(y - 13, 1)})
            y += 46


# ---------------------------------------------------------------- 먹이 그물 · 생태 피라미드
def _check_foodweb(spec):
    if not _need(spec, 'levels'): return ['먹이 그물은 levels(생산자부터 영양 단계별 이름 목록)가 필요합니다.']
    names = [n for row in spec['levels'] for n in row]
    out = [] if len(names) == len(set(names)) else ['같은 이름이 두 번 들어 있습니다.']
    for a, b in spec.get('links', []):
        if a not in names or b not in names: out.append(f'화살표 {a} → {b}의 이름을 확인해 주세요.')
    return out


def _box_edge(c, w, h, toward):
    """상자(중심 c, 폭 w, 높이 h)의 테두리에서 toward 쪽으로 나가는 점."""
    dx, dy = toward[0] - c[0], toward[1] - c[1]
    if not dx and not dy: return c
    t = min(w / 2 / abs(dx) if dx else 1e9, h / 2 / abs(dy) if dy else 1e9)
    return (c[0] + dx * t, c[1] + dy * t)


def _foodweb(spec, parts, labels):
    levels = spec['levels']; names_left = spec.get('level_names') or []
    left = 210 if names_left else 50
    n = len(levels); band = (H - 40) / n
    box = {}
    for g, row in enumerate(levels):           # 영양 단계마다 옅은 띠
        y0 = H - 20 - (g + 1) * band
        parts.append(f'<rect x="{left - 30 if names_left else 20}" y="{y0:.1f}" width="{W - (left - 30 if names_left else 20) - 20:.1f}" height="{band:.1f}" fill="{"#f1f1f1" if g % 2 == 0 else "#fafafa"}" stroke="none"/>')
        y = y0 + band / 2
        step = (W - 40 - left) / len(row)
        for k, name in enumerate(row):
            x = left + step * (k + .5)
            box[name] = (x, y, max(104, _text_width(name, 26) + 36), 50)
        if g < len(names_left): labels.append({**_label(names_left[g], 0, 0, size=22), 'x': 28.0, 'y': round(y - 11, 1)})
    if names_left: parts.append(_line((left - 30, 20), (left - 30, H - 20), 1.2, '4 4'))
    for a, b in spec.get('links', []):      # 화살표는 먹히는 쪽 → 먹는 쪽(에너지 흐름), 상자 테두리에서 시작·끝
        (x1, y1, w1, h1), (x2, y2, w2, h2) = box[a], box[b]
        s = _box_edge((x1, y1), w1 + 6, h1 + 6, (x2, y2)); e = _box_edge((x2, y2), w2 + 8, h2 + 8, (x1, y1))
        parts.append(_arrow(s, e, width=2.2, head=13))
    for name, (x, y, w, h) in box.items():
        parts.append(f'<rect x="{x - w / 2:.1f}" y="{y - h / 2:.1f}" width="{w:.1f}" height="{h}" rx="{h / 2:.1f}" fill="white" stroke="{LINE}" stroke-width="2.2"/>')
        labels.append(_label(name, x, y, size=26))



def _check_pyramid(spec):
    levels = spec.get('levels')
    if not _need(spec, 'levels') or not all(isinstance(x, dict) and x.get('label') is not None for x in levels):
        return ['생태 피라미드는 levels: [{"label":"생산자","value":1000}, …]가 필요합니다(아래부터).']
    if any(not isinstance(x.get('value', 1), (int, float)) or x.get('value', 1) <= 0 for x in levels): return ['value는 양수입니다.']
    return []


def _pyramid(spec, parts, labels):
    """계단식 입체 피라미드: 앞면 폭이 값에 비례하고, 윗면·옆면을 옅게 칠해 두께를 준다."""
    levels = spec['levels']; n = len(levels)
    dx, dy = 34, -18
    hstep = min(104, (H - 90) / n); base = H - 40
    biggest = max(x.get('value', 1) for x in levels)
    shades = ['#f4f4f4', '#e3e3e3', '#d0d0d0', '#bcbcbc', '#a8a8a8', '#959595']
    for i, lv in enumerate(levels):
        frac = lv.get('value', 1) / biggest if spec.get('scaled', True) else 1 - i / (n + 1)
        w = max(80, 740 * frac); y = base - (i + 1) * hstep; x0 = 480 - w / 2
        fill = {'gray': '#cfcfcf', 'dark': GRAY}.get(lv.get('pattern'), shades[min(i, len(shades) - 1)])
        top = [(x0, y), (x0 + w, y), (x0 + w + dx, y + dy), (x0 + dx, y + dy)]
        side = [(x0 + w, y), (x0 + w + dx, y + dy), (x0 + w + dx, y + hstep + dy), (x0 + w, y + hstep)]
        parts.append(_p('M' + 'L'.join(f'{a:.1f},{b:.1f}' for a, b in side) + 'Z', fill='#8f8f8f', width=1.8))
        parts.append(_p('M' + 'L'.join(f'{a:.1f},{b:.1f}' for a, b in top) + 'Z', fill='#fbfbfb', width=1.8))
        parts.append(f'<rect x="{x0:.1f}" y="{y:.1f}" width="{w:.1f}" height="{hstep:.1f}" fill="{fill}" stroke="{LINE}" stroke-width="2.2"/>')
        labels.append(_label(lv['label'], 480, y + hstep / 2, size=26) if w > _text_width(lv['label'], 26) + 30
                      else {**_label(lv['label'], 0, 0, size=26), 'x': round(480 + w / 2 + dx + 14, 1), 'y': round(y + hstep / 2 - 13, 1)})
        if lv.get('note'): labels.append({**_label(lv['note'], 0, 0, size=22), 'x': round(480 + w / 2 + dx + 16, 1), 'y': round(y + hstep / 2 - 11, 1)})



# ---------------------------------------------------------------- 염기 서열
def _check_sequence(spec):
    if not _need(spec, 'strands'): return ['염기 서열은 strands: [{"label":"DNA 주형 가닥","seq":"TACGGA","ends":["3′","5′"]}, …]가 필요합니다.']
    out = []
    for s in spec['strands']:
        seq = str(s.get('seq', '')).upper()
        if not seq or set(seq) - BASES - {'?', '_'}: out.append(f'서열 {s.get("seq")}에는 A, T, G, C, U와 빈칸(?, _)만 씁니다.')
        if len(seq) > 15: out.append('한 가닥은 15염기까지 그릴 수 있습니다.')
    for a, b in spec.get('pairs', []):
        try:
            if len(spec['strands'][a]['seq']) != len(spec['strands'][b]['seq']): out.append('짝을 이루는 두 가닥은 길이가 같아야 합니다.')
        except (IndexError, TypeError): out.append('pairs는 가닥 번호(0부터) 두 개입니다.')
    return out


def _sequence(spec, parts, labels):
    strands = spec['strands']; cell, gap = 44, 4
    left = 230; rowgap = min(150, (H - 120) / max(1, len(strands)))
    top = (H - rowgap * (len(strands) - 1)) / 2
    for r, s in enumerate(strands):
        y = top + r * rowgap; seq = str(s['seq']).upper()
        labels.append({**_label(s.get('label', ''), 0, 0, size=22), 'x': 20.0, 'y': round(y - 11, 1)})
        ends = s.get('ends') or ['', '']
        labels.append(_label(ends[0], left - 26, y, size=22)); labels.append(_label(ends[1], left + len(seq) * (cell + gap) + 22, y, size=22))
        for k, base in enumerate(seq):
            x = left + k * (cell + gap)
            parts.append(f'<rect x="{x:.1f}" y="{y - cell / 2:.1f}" width="{cell}" height="{cell}" fill="white" stroke="{LINE}" stroke-width="2"/>')
            if base not in '?_': labels.append(_label(base, x + cell / 2, y, size=26))
        if s.get('codons'):
            for k in range(0, len(seq) - 2, 3):
                x0 = left + k * (cell + gap) + 3; x1 = x0 + 3 * (cell + gap) - gap - 6; yb = y + cell / 2 + 10
                parts.append(_p(f'M{x0:.1f},{yb - 6:.1f}V{yb:.1f}H{x1:.1f}V{yb - 6:.1f}', width=2))
        # 위에 짝 가닥이 있으면 표시는 아래로(수소 결합 점선과 겹치지 않게)
        below = any(max(pr) == r for pr in spec.get('pairs', []))
        for m in s.get('marks', []):
            x0 = left + m['from'] * (cell + gap) + 2; x1 = left + (m['to'] + 1) * (cell + gap) - gap - 2
            if below:
                yb = y + cell / 2 + (34 if s.get('codons') else 12)
                parts.append(_p(f'M{x0:.1f},{yb - 6:.1f}V{yb:.1f}H{x1:.1f}V{yb - 6:.1f}', width=2))
                labels.append(_label(m.get('label', ''), (x0 + x1) / 2, yb + 20, size=24))
            else:
                yt = y - cell / 2 - 12
                parts.append(_p(f'M{x0:.1f},{yt + 6:.1f}V{yt:.1f}H{x1:.1f}V{yt + 6:.1f}', width=2))
                labels.append(_label(m.get('label', ''), (x0 + x1) / 2, yt - 18, size=24))
    for a, b in spec.get('pairs', []):      # 상보적 염기 사이의 수소 결합을 짧은 점선으로
        ya, yb = top + a * rowgap, top + b * rowgap
        y0, y1 = (ya + cell / 2, yb - cell / 2) if ya < yb else (yb + cell / 2, ya - cell / 2)
        for k in range(len(strands[a]['seq'])):
            x = left + k * (cell + gap) + cell / 2
            parts.append(_line((x, y0 + 4), (x, y1 - 4), width=2, dash='4 4'))


# ---------------------------------------------------------------- 세포 소기관
def _check_cell(spec):
    out = []
    if spec.get('kind', 'animal') not in ('animal', 'plant'): out.append('세포 kind는 animal(동물) 또는 plant(식물)입니다.')
    for m in spec.get('marks', []):
        if m.get('organelle') not in ORGANELLES: out.append('organelle은 ' + ', '.join(ORGANELLES) + ' 중 하나입니다.')
        elif spec.get('kind', 'animal') == 'plant' and m['organelle'] in ('lysosome', 'centriole'):
            out.append(f"식물 세포 그림에는 {ORGANELLES[m['organelle']]}을(를) 그리지 않습니다.")
        elif spec.get('kind', 'animal') == 'animal' and m['organelle'] in ('chloroplast', 'cellwall', 'vacuole'):
            out.append(f"동물 세포에는 {ORGANELLES[m['organelle']]}을(를) 그리지 않습니다.")
    return out


def _smooth(points):
    """닫힌 점열을 매끄러운 곡선(Catmull-Rom → 베지어)으로."""
    n = len(points); d = f'M{points[0][0]:.1f},{points[0][1]:.1f}'
    for i in range(n):
        p0, p1, p2, p3 = points[i - 1], points[i], points[(i + 1) % n], points[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f'C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}'
    return d + 'Z'


def _blob(c, rx, ry, wobble=(.05, .035, .025), n=36):
    """기출 그림처럼 반듯하지 않은 둥근 윤곽. 같은 입력이면 늘 같은 모양이다."""
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        k = 1 + wobble[0] * math.sin(3 * t + .7) + wobble[1] * math.sin(5 * t + 1.9) + wobble[2] * math.sin(7 * t + .3)
        pts.append((c[0] + rx * k * math.cos(t), c[1] + ry * k * math.sin(t)))
    return pts


def _band(c, r0, r1, a0, a1):
    """원호를 따라 휜 납작한 주머니(소포체·골지체 낭). 양 끝은 둥글다."""
    x, y = c; a0, a1 = math.radians(a0), math.radians(a1)
    big = 1 if abs(a1 - a0) > math.pi else 0
    p = lambda r, a: (x + r * math.cos(a), y + r * math.sin(a))
    s0, e0, s1, e1 = p(r0, a0), p(r0, a1), p(r1, a1), p(r1, a0)
    cap = (r1 - r0) / 2
    return (f'M{s0[0]:.1f},{s0[1]:.1f}A{r0:.1f},{r0:.1f} 0 {big} 1 {e0[0]:.1f},{e0[1]:.1f}A{cap:.1f},{cap:.1f} 0 0 0 {s1[0]:.1f},{s1[1]:.1f}'
            f'A{r1:.1f},{r1:.1f} 0 {big} 0 {e1[0]:.1f},{e1[1]:.1f}A{cap:.1f},{cap:.1f} 0 0 0 {s0[0]:.1f},{s0[1]:.1f}Z')


def _nucleus(c, r=78):
    """핵막은 이중막이고 핵공 자리가 끊겨 있다. 인은 회색."""
    x, y = c; out = []
    for k in range(12):
        a0, a1 = math.radians(k * 30 + 4), math.radians(k * 30 + 26)
        for rr in (r, r - 8):
            s, e = (x + rr * math.cos(a0), y + rr * math.sin(a0)), (x + rr * math.cos(a1), y + rr * math.sin(a1))
            out.append(_p(f'M{s[0]:.1f},{s[1]:.1f}A{rr},{rr} 0 0 1 {e[0]:.1f},{e[1]:.1f}', width=2.2))
    out.append(f'<circle cx="{x - r * .12:.1f}" cy="{y + r * .1:.1f}" r="{r * .24:.1f}" fill="{GRAY}" stroke="none"/>')
    return ''.join(out)


def _rough_er(c, r, a0, a1, layers=3):
    """핵을 둘러싼 거친면 소포체: 휜 주머니 여러 겹과 바깥쪽에 붙은 리보솜."""
    out = []
    for i in range(layers):
        r0 = r + 14 + i * 20
        out.append(_p(_band(c, r0, r0 + 8, a0 + i * 6, a1 - i * 4), fill='white', width=2))
        for k in range(int((a1 - a0) / 9)):
            a = math.radians(a0 + i * 6 + 5 + k * 9)
            out.append(f'<circle cx="{c[0] + (r0 + 12) * math.cos(a):.1f}" cy="{c[1] + (r0 + 12) * math.sin(a):.1f}" r="2.6" fill="{LINE}"/>')
    return ''.join(out)


def _golgi(c, rot=0):
    """휜 납작한 주머니가 겹겹이 쌓이고 끝에 작은 소낭이 떨어진다."""
    x, y = c; out = []
    for i in range(5):
        span = 64 - abs(i - 2) * 9
        out.append(_p(_band((x, y + 120), 108 + i * 12, 116 + i * 12, -90 - span / 2, -90 + span / 2), fill='white', width=2))
    for dx, dy, r in ((-58, -2, 6), (60, 4, 7), (-46, 46, 5), (52, 50, 6)):
        out.append(_circle((x + dx, y + dy), r, 'white', 1.8))
    return f'<g transform="rotate({rot} {x} {y})">{"".join(out)}</g>'


def _mito(c, rx=58, ry=28, rot=0):
    """외막과, 위아래에서 번갈아 손가락처럼 접혀 들어간 내막(크리스타)."""
    x, y = c; a, b = rx - 7, ry - 7
    fingers = [-.62, -.31, 0, .31, .62]
    def edge(u, top):
        base = b * math.sqrt(max(0.0, 1 - u * u))
        dip = sum(max(0.0, math.cos((u - f) / .1 * math.pi / 2)) ** 3 for k, f in enumerate(fingers) if (k % 2 == 0) == top and abs(u - f) < .1)
        return base * (1 - .8 * dip)
    n = 120
    top = [(x + a * (-1 + 2 * i / n), y - edge(-1 + 2 * i / n, True)) for i in range(n + 1)]
    bottom = [(x + a * (1 - 2 * i / n), y + edge(1 - 2 * i / n, False)) for i in range(n + 1)]
    inner = 'M' + 'L'.join(f'{px:.1f},{py:.1f}' for px, py in top + bottom) + 'Z'
    return (f'<g transform="rotate({rot} {x} {y})"><ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="white" stroke="{LINE}" stroke-width="2.4"/>'
            f'{_p(inner, width=1.6)}</g>')


def _chloro(c, rx=66, ry=32, rot=0):
    """이중막, 틸라코이드가 쌓인 그라나, 그라나를 잇는 라멜라."""
    x, y = c; out = [f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="white" stroke="{LINE}" stroke-width="2.4"/>',
                     f'<ellipse cx="{x}" cy="{y}" rx="{rx - 6}" ry="{ry - 6}" fill="none" stroke="{LINE}" stroke-width="1.4"/>']
    xs = [x - rx * .55, x - rx * .18, x + rx * .2, x + rx * .55]
    out.append(_p(f'M{xs[0]:.1f},{y:.1f}H{xs[-1]:.1f}', width=1.4))
    for k, gx in enumerate(xs):
        h = 5 if k in (0, 3) else 6
        for j in range(h):
            yy = y - h * 3.2 + j * 6.4
            out.append(f'<rect x="{gx - 11:.1f}" y="{yy:.1f}" width="22" height="5" rx="2.5" fill="{GRAY}" stroke="{LINE}" stroke-width="1"/>')
    return f'<g transform="rotate({rot} {x} {y})">{"".join(out)}</g>'


def _lysosome(c, r=17):
    x, y = c
    dots = ''.join(f'<circle cx="{x + dx:.1f}" cy="{y + dy:.1f}" r="2.2" fill="{LINE}"/>' for dx, dy in ((-5, -4), (5, -2), (-1, 6), (6, 6)))
    return _circle(c, r, 'white', 2) + dots


def _centriole(c):
    x, y = c
    a = f'<rect x="{x - 18:.1f}" y="{y - 8:.1f}" width="36" height="16" fill="white" stroke="{LINE}" stroke-width="1.8"/>' + ''.join(_line((x - 18 + k * 6, y - 8), (x - 18 + k * 6, y + 8), 1.2) for k in range(1, 6))
    b = f'<rect x="{x + 22:.1f}" y="{y - 22:.1f}" width="16" height="36" fill="white" stroke="{LINE}" stroke-width="1.8"/>' + ''.join(_line((x + 22, y - 22 + k * 6), (x + 38, y - 22 + k * 6), 1.2) for k in range(1, 6))
    return a + b


def _cell(spec, parts, labels):
    plant = spec.get('kind', 'animal') == 'plant'
    if plant and spec.get('shape', 'hex') == 'hex':
        # 교과서 식물 세포 그림 꼴: 조직 속 육각형 세포. 회색 띠 세포벽, 꼭짓점마다 이웃 세포의 벽이 이어지고 원형질 연락사 자리가 끊긴다.
        cx, cy = 480, 322
        outer = [(480, 38), (770, 150), (770, 492), (480, 604), (190, 492), (190, 150)]
        shrink = lambda pts, k: [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in pts]
        inner = shrink(outer, .94)
        poly = lambda pts: 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in pts) + 'Z'
        for (x, y) in outer:      # 이웃 세포의 벽: 꼭짓점에서 바깥으로 뻗는 띠
            dx, dy = x - cx, y - cy; n = math.hypot(dx, dy); ux, uy = dx / n, dy / n; px, py = -uy * 9, ux * 9
            far = (x + ux * 70, y + uy * 70)
            parts.append(f'<path d="M{x + px:.1f},{y + py:.1f}L{far[0] + px:.1f},{far[1] + py:.1f}L{far[0] - px:.1f},{far[1] - py:.1f}L{x - px:.1f},{y - py:.1f}Z" fill="#c9c9c9" stroke="none"/>')
            parts.append(f'<path d="M{x + px:.1f},{y + py:.1f}L{far[0] + px:.1f},{far[1] + py:.1f}M{x - px:.1f},{y - py:.1f}L{far[0] - px:.1f},{far[1] - py:.1f}" stroke="{LINE}" stroke-width="2.2" fill="none"/>')
        parts.append(f'<path d="{poly(outer)}{poly(inner)}" fill="#c9c9c9" fill-rule="evenodd" stroke="{LINE}" stroke-width="2.4"/>')
        for a, b, t in ((outer[1], outer[2], .3), (outer[4], outer[5], .65), (outer[2], outer[3], .55)):      # 원형질 연락사
            mx, my = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            ix, iy = cx + (mx - cx) * .94, cy + (my - cy) * .94
            ex, ey = (b[0] - a[0]) / math.hypot(b[0] - a[0], b[1] - a[1]) * 5, (b[1] - a[1]) / math.hypot(b[0] - a[0], b[1] - a[1]) * 5
            parts.append(f'<path d="M{mx - ex:.1f},{my - ey:.1f}L{mx + ex:.1f},{my + ey:.1f}L{ix + ex:.1f},{iy + ey:.1f}L{ix - ex:.1f},{iy - ey:.1f}Z" fill="white" stroke="none"/>')
            parts.append(_line((mx - ex, my - ey), (ix - ex, iy - ey), 1.4) + _line((mx + ex, my + ey), (ix + ex, iy + ey), 1.4))
        parts.append(_p(poly(shrink(outer, .91)), width=1.6))      # 세포막
        parts.append(_p(_smooth(_blob((505, 375), 175, 112, (.05, .03, .02))), fill='white', width=2.2))      # 액포
        nuc = (410, 205)
        where = {'nucleus': nuc, 'er': (505, 205), 'golgi': (275, 330), 'mitochondria': (640, 270), 'chloroplast': (335, 500),
                 'ribosome': (560, 120), 'vacuole': (520, 380), 'cellwall': (770, 330), 'membrane': (220, 410)}
        parts.append(_rough_er(nuc, 62, -60, 70, layers=2))
        parts.append(_nucleus(nuc, 62))
        parts += [_golgi((275, 330), rot=-90), _mito((640, 262), rx=46, ry=22, rot=40), _mito((480, 540), rx=44, ry=21, rot=-5),
                  _chloro((335, 500), rx=58, ry=27, rot=28), _chloro((640, 495), rx=58, ry=27, rot=-28), _chloro((300, 205), rx=50, ry=24, rot=-35)]
        dots = [(560, 120), (585, 145), (535, 100), (250, 420), (700, 380), (430, 115), (400, 500)]
    elif plant:
        # 기출(2018 6월·2020 6월 생명과학Ⅰ 1번) 꼴: 세포벽 때문에 모서리만 둥근 직사각형. 벽은 회색 띠, 그 안쪽에 얇은 세포막.
        x0, y0, x1, y1, t = 130, 60, 870, 580, 16
        rect = lambda a, b, c, d, r: f'M{a + r},{b}H{c - r}A{r},{r} 0 0 1 {c},{b + r}V{d - r}A{r},{r} 0 0 1 {c - r},{d}H{a + r}A{r},{r} 0 0 1 {a},{d - r}V{b + r}A{r},{r} 0 0 1 {a + r},{b}Z'
        parts.append(f'<path d="{rect(x0, y0, x1, y1, 26)}{rect(x0 + t, y0 + t, x1 - t, y1 - t, 14)}" fill="#c9c9c9" fill-rule="evenodd" stroke="{LINE}" stroke-width="2.4"/>')
        parts.append(_p(rect(x0 + t + 6, y0 + t + 6, x1 - t - 6, y1 - t - 6, 10), width=1.6))      # 세포막
        bean = [(720 + 105 * math.cos(a) * (1 - .32 * max(0.0, math.cos(a + math.pi)) ** 3), 320 + 175 * math.sin(a)) for a in [2 * math.pi * k / 40 for k in range(40)]]
        parts.append(_p(_smooth(bean), fill='white', width=2.2))      # 액포: 세로로 선 콩팥 모양
        nuc = (395, 330)
        where = {'nucleus': nuc, 'er': (485, 300), 'golgi': (520, 165), 'mitochondria': (255, 330), 'chloroplast': (245, 165),
                 'ribosome': (330, 470), 'vacuole': (725, 330), 'cellwall': (x0 + t / 2, 320), 'membrane': (x0 + t + 6, 440)}
        parts.append(_rough_er(nuc, 68, -70, 75, layers=2))
        parts.append(_nucleus(nuc, 68))
        parts += [_golgi((520, 165), rot=0), _mito((255, 330), rot=80), _mito((470, 515), rx=46, ry=22, rot=-8),
                  _chloro((245, 165), rx=60, ry=28, rot=-22), _chloro((250, 495), rx=60, ry=28, rot=18), _chloro((630, 515), rx=58, ry=27, rot=-6)]
        dots = [(330, 470), (355, 500), (300, 445), (560, 400), (585, 255), (400, 120), (180, 255), (560, 330)]
    else:
        parts.append(_p(_smooth(_blob((480, 320), 400, 272, (.03, .022, .012))), fill='white', width=3))   # 세포막
        nuc = (430, 310)
        where = {'nucleus': nuc, 'er': (330, 395), 'golgi': (670, 330), 'mitochondria': (190, 330), 'ribosome': (560, 480),
                 'lysosome': (690, 470), 'centriole': (260, 165), 'membrane': (878, 300)}
        parts.append(_rough_er(nuc, 78, 95, 250))
        parts.append(_nucleus(nuc, 78))
        parts += [_golgi((670, 330), rot=80), _mito((190, 330), rot=-70), _mito((600, 135), rx=50, ry=24, rot=15),
                  _lysosome((690, 470)), _lysosome((610, 520), 13), _centriole((240, 160))]
        dots = [(560, 480), (520, 440), (595, 455), (300, 500), (790, 230), (760, 400), (360, 150), (480, 560), (150, 210), (820, 330)]
    parts += [f'<circle cx="{a:.1f}" cy="{b:.1f}" r="4" fill="{LINE}"/>' for a, b in dots]      # 떠 있는 리보솜
    # 이름표는 가까운 쪽 가장자리에 두고, 같은 쪽 이름표끼리는 46px 이상 띄운다
    placed = []
    for m in spec.get('marks', []):
        ax, ay = where[m['organelle']]
        side = {'left': -1, 'right': 1}.get(m.get('side'), 1 if ax >= 480 else -1)
        placed.append([side, ay + m.get('dy', 0), ax, ay, m.get('label', '')])
    for side in (-1, 1):
        # 높이가 비슷하면 가장자리에 가까운 것이 위로 가야 지시선끼리 엇갈리지 않는다
        row = sorted((p for p in placed if p[0] == side), key=lambda p: (round(p[1] / 40), p[2] * -side))
        for k in range(1, len(row)): row[k][1] = max(row[k][1], row[k - 1][1] + 46)
        shift = max(0, (row[-1][1] if row else 0) - (H - 30))
        for p in row: p[1] = max(30, p[1] - shift)
    for side, ly, ax, ay, text in placed:
        lx = 975 if side > 0 else 25
        parts.append(_line((ax, ay), (lx - side * 30, ly), width=1.6))
        parts.append(f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="3" fill="{LINE}"/>')
        labels.append(_label(text, lx - side * 8, ly, size=28))


# ---------------------------------------------------------------- 반응 입자 모형
SHADES = {'white': ('#ffffff', '#cfcfcf'), 'light': ('#f4f4f4', '#9d9d9d'), 'gray': ('#d9d9d9', '#5e5e5e'), 'dark': ('#8a8a8a', '#161616')}
SHADE_ORDER = ['gray', 'white', 'dark', 'light']
RADIUS = {'H': 11, 'He': 11, 'Li': 19, 'Be': 16, 'B': 15, 'C': 15, 'N': 15, 'O': 15, 'F': 14, 'Ne': 14,
          'Na': 21, 'Mg': 20, 'Al': 19, 'Si': 18, 'P': 18, 'S': 18, 'Cl': 18, 'Ar': 18, 'K': 23, 'Ca': 22}
FALLBACK_R = [18, 12, 15, 14]


def _check_particles(spec):
    if not _need(spec, 'panels') or len(spec['panels']) > 3: return ['입자 모형은 panels(1~3칸: 반응 전, 반응 후 등)가 필요합니다.']
    out = []
    for panel in spec['panels']:
        for mol in panel.get('molecules', []):
            if not 1 <= len(mol.get('atoms', [])) <= 5: out.append('분자 하나는 원자 1~5개입니다.')
            if not 1 <= mol.get('count', 1) <= 12: out.append('같은 분자는 12개까지 그립니다.')
    elements = {a for p in spec['panels'] for m in p.get('molecules', []) for a in m.get('atoms', [])}
    if len(elements) > 4: out.append('원소는 4종류까지 구별해 그립니다.')
    if spec.get('container', 'circle') not in ('circle', 'box', 'cylinder'): out.append('container는 circle, box, cylinder 중 하나입니다.')
    return out


def _atom_defs(parts):
    stops = ''.join(f'<radialGradient id="atom_{k}" cx=".36" cy=".32" r=".72"><stop offset="0" stop-color="{a}"/><stop offset=".45" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></radialGradient>'
                    for k, (a, b) in SHADES.items())
    parts.append(f'<defs>{stops}</defs>')


def _molecule_layout(atoms, radius):
    """원자 중심의 상대 위치(분자 모양). 가운데 원자는 하나뿐인 원자 중 가장 큰 것."""
    n = len(atoms); rs = [radius[a] for a in atoms]
    if n == 1: return [(0, 0)]
    if n == 2:
        d = (rs[0] + rs[1]) * .78
        return [(-d * rs[1] / (rs[0] + rs[1]), 0), (d * rs[0] / (rs[0] + rs[1]), 0)]
    singles = [i for i, a in enumerate(atoms) if atoms.count(a) == 1] or [0]
    c = max(singles, key=lambda i: rs[i])
    others = [i for i in range(n) if i != c]
    if n == 3: angles = [180, 0] if atoms[c] in ('C', 'Be') else [-142, -38]
    elif n == 4: angles = [-90, 30, 150]
    else: angles = [-90, 0, 90, 180]
    pos = [(0, 0)] * n
    for i, ang in zip(others, angles):
        d = (rs[c] + rs[i]) * .8; t = math.radians(ang)
        pos[i] = (d * math.cos(t), d * math.sin(t))
    return pos


def _particles(spec, parts, labels):
    import random
    _atom_defs(parts)
    panels = spec['panels']; n = len(panels)
    elements = []
    for p in panels:
        for m in p.get('molecules', []):
            for a in m['atoms']:
                if a not in elements: elements.append(a)
    custom = spec.get('elements') or {}
    radius, shade = {}, {}
    for i, e in enumerate(elements):
        radius[e] = (custom.get(e) or {}).get('r') or RADIUS.get(e, FALLBACK_R[i % 4])
        shade[e] = (custom.get(e) or {}).get('shade') or SHADE_ORDER[i % 4]
    scale = spec.get('atom_scale', 1.5)
    radius = {e: r * scale for e, r in radius.items()}
    legend_w = 150
    gap = 96
    avail = W - 40 - legend_w - (n - 1) * gap
    kind = spec.get('container', 'circle')
    size = min(avail / n, 470)
    top = max(30, (H - size - 50) / 2)
    boxes = []
    for i, p in enumerate(panels):
        x0 = 30 + i * (size + gap) + (avail - n * size) / 2
        cx, cy = x0 + size / 2, top + size / 2
        t0 = top + size * .18
        if kind == 'circle': inside = lambda q, m, cx=cx, cy=cy: math.dist(q, (cx, cy)) <= size / 2 - m - 8
        elif kind == 'box': inside = lambda q, m, x0=x0: x0 + m + 10 <= q[0] <= x0 + size - m - 10 and top + m + 10 <= q[1] <= top + size - m - 10
        else: inside = lambda q, m, x0=x0: x0 + m + 10 <= q[0] <= x0 + size - m - 10 and t0 + m + 8 <= q[1] <= top + size - m - 10
        boxes.append((x0, cx, cy, t0, inside))

    def place(i, factor):
        """겹치지 않게 아무렇게나 흩어 놓고, 저마다 다른 방향으로 돌린다. (자리 목록, 가장 좁은 틈)"""
        x0, cx, cy, t0, inside = boxes[i]
        rad = {e: r * factor for e, r in radius.items()}
        mols = [m['atoms'] for m in panels[i].get('molecules', []) for _ in range(m.get('count', 1))]
        rng = random.Random(spec.get('seed', 7) * 31 + i)
        rng.shuffle(mols)
        placed, out, worst = [], [], 1e9
        for atoms in mols:
            lay = _molecule_layout(atoms, rad); rot = rng.uniform(0, 2 * math.pi)
            lay = [(x * math.cos(rot) - y * math.sin(rot), x * math.sin(rot) + y * math.cos(rot)) for x, y in lay]
            reach = max(math.hypot(x, y) + rad[a] for (x, y), a in zip(lay, atoms))
            best, best_room = None, -1e9
            for _ in range(700):
                q = (rng.uniform(x0, x0 + size), rng.uniform(top, top + size))
                if not inside(q, reach): continue
                room = min([math.dist(q, c) - reach - r2 for c, r2 in placed] or [1e9])
                if room > best_room: best, best_room = q, room
                if room > 10: break
            q = best or (cx, cy)
            worst = min(worst, best_room if best else -1e9)
            placed.append((q, reach)); out.append((q, lay, atoms, rad))
        return out, worst
    for factor in (1, .9, .8, .72, .64, .56):      # 붐비면 원자를 조금씩 줄인다(모든 칸 같은 비율)
        layouts = [place(i, factor) for i in range(n)]
        if all(w >= 3 for _, w in layouts): break
    for i, p in enumerate(panels):
        x0, cx, cy, t0, inside = boxes[i]
        if kind == 'circle':
            parts.append(_circle((cx, cy), size / 2, 'white', 2.4))
        elif kind == 'box':
            parts.append(f'<rect x="{x0:.1f}" y="{top:.1f}" width="{size:.1f}" height="{size:.1f}" rx="10" fill="white" stroke="{LINE}" stroke-width="2.4"/>')
        else:      # 실린더와 피스톤
            parts.append(_p(f'M{x0:.1f},{top:.1f}V{top + size:.1f}H{x0 + size:.1f}V{top:.1f}', width=2.6))
            parts.append(f'<rect x="{x0 + 3:.1f}" y="{t0 - 22:.1f}" width="{size - 6:.1f}" height="22" fill="#b5b5b5" stroke="{LINE}" stroke-width="2"/>')
            parts.append(f'<rect x="{cx - 8:.1f}" y="{top - 30:.1f}" width="16" height="{t0 - 22 - top + 30:.1f}" fill="#d6d6d6" stroke="{LINE}" stroke-width="1.8"/>')
        if p.get('label'): labels.append(_label(p['label'], cx, top + size + 30, size=26))
        for q, lay, atoms, rad in layouts[i][0]:
            order = sorted(range(len(atoms)), key=lambda k: (rad[atoms[k]], -lay[k][1]))      # 작은 원자를 뒤에
            for k in order:
                a = atoms[k]; c = (q[0] + lay[k][0], q[1] + lay[k][1])
                parts.append(f'<circle cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="{rad[a]:.1f}" fill="url(#atom_{shade[a]})" stroke="{LINE}" stroke-width="1.8"/>')
        if i < n - 1:
            ax = x0 + size + 18
            parts.append(_arrow((ax, cy), (ax + gap - 36, cy), width=3, head=18))
    ly = top + size / 2 - (len(elements) - 1) * 26
    lx = boxes[-1][0] + size + 44
    for e in elements:      # 범례: 오른쪽에 세로로
        r = min(radius[e] * factor, 17)
        parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="{r:.1f}" fill="url(#atom_{shade[e]})" stroke="{LINE}" stroke-width="1.8"/>')
        labels.append({**_label(e, 0, 0, size=26), 'x': float(lx + 26), 'y': round(ly - 14, 1)})
        ly += 52


# ---------------------------------------------------------------- 반응 경로-에너지
def _check_energy(spec):
    out = []
    for key in ('reactant', 'product', 'peak'):
        if not isinstance(spec.get(key), (int, float)): out.append(f'{key}(에너지 값)가 필요합니다.')
    if not out and spec['peak'] <= max(spec['reactant'], spec['product']): out.append('peak(활성화 상태)는 반응물과 생성물보다 높아야 합니다.')
    if 'catalyst' in spec and not (max(spec.get('reactant', 0), spec.get('product', 0)) < spec['catalyst'] < spec.get('peak', 0)):
        out.append('catalyst는 반응물·생성물보다 높고 peak보다 낮아야 합니다.')
    return out


def _energy(spec, parts, labels):
    lo = min(spec['reactant'], spec['product']); hi = spec['peak']
    y = lambda v: 520 - (v - lo) / (hi - lo) * 400
    parts.append(_arrow((110, 580), (110, 50), width=2.5)); parts.append(_arrow((110, 580), (960, 580), width=2.5))
    labels.append({**_label(spec.get('y_label', '에너지'), 0, 0, size=24), 'x': 120.0, 'y': 40.0})
    labels.append({**_label(spec.get('x_label', '반응 경로'), 0, 0, size=24), 'x': 830.0, 'y': 594.0})
    yr, yp = y(spec['reactant']), y(spec['product'])

    def curve(peak, dash=''):
        yt = y(peak)
        return _p(f'M150,{yr:.1f}H300C380,{yr:.1f} 420,{yt:.1f} 520,{yt:.1f}C620,{yt:.1f} 660,{yp:.1f} 740,{yp:.1f}H910', width=3, dash=dash)
    parts.append(curve(spec['peak']))
    if 'catalyst' in spec: parts.append(curve(spec['catalyst'], '9 7'))
    names = spec.get('names', {})
    if names.get('reactant'): labels.append(_label(names['reactant'], 220, yr - 28, size=24))
    if names.get('product'): labels.append(_label(names['product'], 830, yp - 28, size=24))
    level = {'reactant': spec['reactant'], 'product': spec['product'], 'peak': spec['peak'], 'catalyst': spec.get('catalyst', spec['peak'])}
    anchor = {'reactant': 300, 'product': 740, 'peak': 520, 'catalyst': 520}      # 그 높이가 곡선에 닿는 곳
    for i, m in enumerate(spec.get('marks', [])):
        a, b = y(level[m['from']]), y(level[m['to']])
        x = 340 + i * 110 if m['to'] in ('peak', 'catalyst') else 800 - i * 20
        for key, v in ((m['from'], a), (m['to'], b)):      # 높이를 화살표까지 점선으로 끌어온다
            x0, x1 = sorted((anchor[key], x))
            parts.append(_line((x0 - 14, v), (x1 + 14, v), width=1.5, dash='5 4'))
        parts.append(_double_arrow((x, a), (x, b)))
        labels.append(_label(m.get('label', ''), x + 34, (a + b) / 2, size=24))


CHECK = {'pedigree': _check_pedigree, 'foodweb': _check_foodweb, 'pyramid': _check_pyramid, 'sequence': _check_sequence,
         'cell': _check_cell, 'particles': _check_particles, 'energy': _check_energy}
RENDER = {'pedigree': _pedigree, 'foodweb': _foodweb, 'pyramid': _pyramid, 'sequence': _sequence, 'cell': _cell,
          'particles': _particles, 'energy': _energy}

PROMPT = """
도식 자료: 가계도, 먹이 그물, 생태 피라미드, 염기 서열, 세포 소기관, 반응 입자 모형, 반응 경로-에너지 그래프는 AI가 그리지 않고 앱이 그린다. 해당 그림 자료의 image_mode는 strict, image_creative와 image_text_*는 빈 문자열로 두고, image_locked 첫 글자부터 `도식: ` 뒤에 JSON 하나만 쓴다. 글씨는 평문이다(LaTeX 금지).
- 가계도: {"type":"pedigree","generations":[["1","2"],["3","4","5"]],"people":[{"id":"1","sex":"M","trait":"a"},{"id":"2","sex":"F","trait":"","carrier":false},…],"couples":[["1","2"]],"children":[{"parents":["1","2"],"kids":["3","4"]}],"traits":{"a":"유전병 ㉠ 발현","b":"…"}} trait는 ""(정상), "a", "b", "ab". 세대마다 왼쪽부터 순서대로 쓴다. 범례는 앱이 만든다.
- 먹이 그물: {"type":"foodweb","levels":[["벼","풀"],["메뚜기","토끼"],["개구리"],["뱀"]],"links":[["벼","메뚜기"],…],"level_names":["생산자","1차 소비자",…]} levels는 생산자부터, links는 먹히는 쪽 → 먹는 쪽(에너지 흐름).
- 생태 피라미드: {"type":"pyramid","levels":[{"label":"생산자","value":1000},{"label":"1차 소비자","value":100},…]} 아래부터. value에 비례한 폭(scaled:false면 같은 비율로 줄임).
- 염기 서열: {"type":"sequence","strands":[{"label":"DNA 주형 가닥","seq":"TACGGACTT","ends":["3′","5′"]},{"label":"mRNA","seq":"AUGCCUGAA","ends":["5′","3′"],"codons":true,"marks":[{"from":3,"to":5,"label":"㉠"}]}],"pairs":[[0,1]]} 가닥당 15염기 이하. 빈칸은 ?로 쓴다. codons는 세 염기씩 묶음 표시.
- 세포 소기관: {"type":"cell","kind":"animal|plant","shape":"hex|rect"(식물만, 기본 hex 조직 속 육각형 세포),"marks":[{"organelle":"nucleus|mitochondria|chloroplast|golgi|er|ribosome|lysosome|centriole|vacuole|cellwall|membrane","label":"A"}]} 표시는 A~E로 하고 소기관 이름은 쓰지 않는다.
- 반응 입자 모형: {"type":"particles","panels":[{"label":"반응 전","molecules":[{"atoms":["H","H"],"count":3},{"atoms":["N","N"],"count":1}]},{"label":"반응 후","molecules":[{"atoms":["N","H","H","H"],"count":2}]}]} 원자 수가 보존되게 쓴다. 원소는 4종류까지, 범례는 앱이 만든다.
- 반응 경로-에너지: {"type":"energy","reactant":0,"product":-40,"peak":60,"catalyst":30,"names":{"reactant":"반응물","product":"생성물"},"marks":[{"from":"reactant","to":"peak","label":"(가)"},{"from":"reactant","to":"product","label":"(나)"}]} 값은 상대적인 에너지다.
가계도·입자 모형처럼 수가 답에 영향을 주는 도식은 명세의 수가 문항의 조건과 맞는지 review_note에 적는다.
"""

from . import diagrams_physics as _phys      # noqa: E402  (물리 도식은 위의 그리기 도구를 쓴다)
CHECK.update(_phys.CHECK); RENDER.update(_phys.RENDER)
PROMPT += _phys.PROMPT
