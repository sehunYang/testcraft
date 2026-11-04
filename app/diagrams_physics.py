"""물리 도식: 역학 상황 · 회로 · 그래프 · 여러 칸 묶음. 평가원 그림 꼴을 따른다.

좌표는 모두 '세계 좌표'(y가 위로 커짐)로 받고, 앱이 그림 칸에 맞게 늘이거나 줄인다.
물체·도르래·부품의 크기는 화면 픽셀로 고정해 어떤 장면에서도 같은 크기로 보인다.
글씨는 글씨 레이어로 따로 둔다($...$ 로 쓴 글씨는 수식 글꼴).
"""
import math
import re

from .diagrams import LINE, W, H, _p, _line, _arrow, _circle, _text_width, _need
from .maps import _label, _plain

LIGHT, PALE = '#d4d4d4', '#ececec'
FRAME = (0, 0, W, H)


# ---------------------------------------------------------------- 공통
def _width(text, size):
    """글씨 폭 어림. LaTeX 명령은 한 글자, 첨자는 작게 센다."""
    t = re.sub(r'\\(?:mathrm|text)\{([^}]*)\}', r'\1', str(text)).replace('$', '').replace('\\,', ' ')
    t = re.sub(r'\\[A-Za-z]+', 'x', t)
    t = re.sub(r'[_^]\{([^}]*)\}', lambda m: m.group(1)[:max(1, len(m.group(1)) * 2 // 3)], t)
    return _text_width(t.replace('{', '').replace('}', '').replace('_', '').replace('^', ''), size)


TEXT = 1.4       # 시험지에서 본문 글씨와 비슷하게 보이도록(2026-11-04)


def _lab(text, x, y, size=26, scaled=False):
    """글씨 하나. $가 있으면 수식 글씨(physics), 없으면 한글 글씨."""
    text = str(text)
    if not scaled: size = round(size * TEXT)
    if '$' not in text: return _label(text, x, y, size=size)
    wide = _width(text, size)
    return {'kind': 'physics', 'text': text, 'x': round(max(8, min(W - wide - 8, x - wide / 2)), 1),
            'y': round(max(8, min(H - size - 8, y - size / 2)), 1), 'size': size, 'rotation': 0}


def _lab_side(text, x, y, side, size=26, gap=10):
    """기준점의 한쪽(left/right/up/down)에 붙여 놓는다."""
    size = round(size * TEXT)
    wide = _width(text, size)
    dx = {'left': -(wide / 2 + gap), 'right': wide / 2 + gap}.get(side, 0)
    dy = {'up': -(size / 2 + gap), 'down': size / 2 + gap}.get(side, 0)
    return _lab(text, x + dx, y + dy, size, scaled=True)


class Fit:
    """세계 좌표 → 그림 칸 픽셀. 가로세로 같은 배율."""

    def __init__(self, pts, box, pad=(70, 60, 70, 70)):
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        bw = box[2] - box[0] - pad[0] - pad[2]; bh = box[3] - box[1] - pad[1] - pad[3]
        w = max(x1 - x0, 1e-9); h = max(y1 - y0, 1e-9)
        self.s = min(bw / w, bh / h) if (x1 - x0) and (y1 - y0) else (bw / w if x1 - x0 else bh / h)
        self.ox = box[0] + pad[0] + (bw - (x1 - x0) * self.s) / 2 - x0 * self.s
        self.oy = box[1] + pad[1] + (bh - (y1 - y0) * self.s) / 2 + y1 * self.s

    def __call__(self, p):
        return (self.ox + p[0] * self.s, self.oy - p[1] * self.s)


def _defs(parts):
    """회색 띠(벽), 바닥, 구(공·원자)의 음영."""
    if any('id="wallfade"' in x for x in parts): return
    parts.append('<defs>'
                 '<linearGradient id="wallfade" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#8f8f8f"/><stop offset="1" stop-color="#ffffff"/></linearGradient>'
                 '<linearGradient id="wallfadeL" x1="1" y1="0" x2="0" y2="0"><stop offset="0" stop-color="#8f8f8f"/><stop offset="1" stop-color="#ffffff"/></linearGradient>'
                 '<linearGradient id="tablefade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e6e6e6"/><stop offset=".35" stop-color="#f6f6f6"/><stop offset="1" stop-color="#ffffff"/></linearGradient><linearGradient id="groundfade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d9d9d9"/><stop offset="1" stop-color="#ffffff"/></linearGradient>'
                 '<radialGradient id="ball" cx=".38" cy=".34" r=".7"><stop offset="0" stop-color="#ffffff"/><stop offset=".55" stop-color="#e2e2e2"/><stop offset="1" stop-color="#8a8a8a"/></radialGradient>'
                 '</defs>')


def _poly(points, close=False):
    d = 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in points)
    return d + ('Z' if close else '')


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _pt(v):
    return isinstance(v, (list, tuple)) and len(v) == 2 and all(_num(a) for a in v)


# ---------------------------------------------------------------- 역학 상황
def _check_mechanics(spec):
    out = []
    track = spec.get('track', [])
    if track and (not isinstance(track, list) or len(track) < 2 or not all(_pt(p) for p in track)):
        out.append('track은 [[x,y],[x,y],…] 꼴의 점 2개 이상입니다(y는 위로 커짐).')
    elif track and any(b[0] <= a[0] for a, b in zip(track, track[1:])):
        out.append('track의 x는 왼쪽에서 오른쪽으로 커져야 합니다.')
    if not track and not spec.get('objects') and not spec.get('pulleys'): out.append('역학 상황은 track(바닥·빗면) 또는 objects가 필요합니다.')
    for o in spec.get('objects', []):
        if o.get('kind', 'block') not in ('block', 'ball', 'cart'): out.append('objects의 kind는 block, ball, cart 중 하나입니다.')
        if 'on' in o and not track: out.append('on으로 놓을 물체에는 track이 필요합니다.')
        if 'on' not in o and not _pt(o.get('at')) and not o.get('hang'): out.append('물체는 on(바닥 위 x), at([x,y]), hang(도르래 이름) 중 하나로 놓습니다.')
        if o.get('hang') and o['hang'] not in {pl.get('id', f'P{k}') for k, pl in enumerate(spec.get('pulleys', []))}: out.append(f"hang할 도르래 {o['hang']}이(가) 없습니다.")
        if 'on' in o and track and not (track[0][0] <= o['on'] <= track[-1][0]): out.append(f"물체의 on={o['on']}이 track 밖입니다.")
    return out


def _track_at(track, x):
    """x에서 바닥의 높이와 기울기(라디안)."""
    for a, b in zip(track, track[1:]):
        if a[0] <= x <= b[0]:
            t = (x - a[0]) / (b[0] - a[0])
            return a[1] + t * (b[1] - a[1]), math.atan2(b[1] - a[1], b[0] - a[0])
    a, b = (track[0], track[1]) if x < track[0][0] else (track[-2], track[-1])
    return (a[1] if x < track[0][0] else b[1]), math.atan2(b[1] - a[1], b[0] - a[0])


def _rounded(points, r=22):
    """꺾이는 곳을 살짝 둥글게(기출의 빗면 아래 곡선)."""
    if len(points) < 3 or not r: return _poly(points)
    d = f'M{points[0][0]:.1f},{points[0][1]:.1f}'
    for i in range(1, len(points) - 1):
        p0, p1, p2 = points[i - 1], points[i], points[i + 1]
        l1 = math.dist(p0, p1); l2 = math.dist(p1, p2)
        rr = min(r, l1 / 2, l2 / 2)
        a = (p1[0] + (p0[0] - p1[0]) * rr / l1, p1[1] + (p0[1] - p1[1]) * rr / l1)
        b = (p1[0] + (p2[0] - p1[0]) * rr / l2, p1[1] + (p2[1] - p1[1]) * rr / l2)
        d += f'L{a[0]:.1f},{a[1]:.1f}Q{p1[0]:.1f},{p1[1]:.1f} {b[0]:.1f},{b[1]:.1f}'
    return d + f'L{points[-1][0]:.1f},{points[-1][1]:.1f}'


def _hatch(a, b, side=1, step=12, size=10, width=1.4):
    """고정된 면(천장·받침)의 빗금. side는 선의 어느 쪽에 칠할지(+1 왼쪽 법선)."""
    L = math.dist(a, b); ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    nx, ny = -uy * side, ux * side
    out = [_line(a, b, 2.5)]
    k = step / 2
    while k < L:
        p = (a[0] + ux * k, a[1] + uy * k)
        out.append(_line(p, (p[0] + nx * size + ux * size * .7, p[1] + ny * size + uy * size * .7), width))
        k += step
    return ''.join(out)


def _spring(a, b, coils=None, amp=17, lead=12):
    """감긴 코일 용수철(교과서·기출 꼴): 고리가 겹쳐 보이는 늘어진 사이클로이드."""
    L = math.dist(a, b)
    if L < 2 * lead + 20: lead = L / 5
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L; nx, ny = -uy, ux
    body = L - 2 * lead
    n = coils or max(4, min(14, round(body / 34)))
    c = body / (2 * math.pi * n); k = max(c * 2.1, amp * .62)
    t0 = -math.pi / 2; steps = n * 28
    x0 = c * t0 + k * math.sin(t0)
    pts = [a]
    for i in range(steps + 1):
        t = t0 + 2 * math.pi * n * i / steps
        along = lead + (c * t + k * math.sin(t) - x0); perp = amp * math.cos(t)
        pts.append((a[0] + ux * along + nx * perp, a[1] + uy * along + ny * perp))
    pts.append(b)
    return _p(_poly(pts), width=1.9)


def _box_corners(c, w, h, ang):
    """중심 c, 회전 ang(라디안, 화면 좌표에서 반시계)."""
    ca, sa = math.cos(ang), math.sin(ang)
    out = []
    for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        out.append((c[0] + dx * ca + dy * sa, c[1] - dx * sa + dy * ca))
    return out


def _tangent(c, r, p, away):
    """점 p에서 원(c, r)에 그은 접점 중, away 쪽(줄이 감기는 바깥)에 있는 것."""
    d = math.dist(c, p)
    if d <= r + 1: return (c[0] + r * away[0], c[1] + r * away[1])
    base = math.atan2(p[1] - c[1], p[0] - c[0]); off = math.acos(r / d)
    cands = [(c[0] + r * math.cos(base + s * off), c[1] + r * math.sin(base + s * off)) for s in (1, -1)]
    return max(cands, key=lambda t: (t[0] - c[0]) * away[0] + (t[1] - c[1]) * away[1])


def _mechanics(spec, parts, labels, box=FRAME):
    _defs(parts)
    track = [tuple(p) for p in spec.get('track', [])]
    world = list(track)
    world += [tuple(o['at']) for o in spec.get('objects', []) if _pt(o.get('at'))]
    world += [tuple(p['at']) for p in spec.get('pulleys', []) if _pt(p.get('at'))]
    for w_ in spec.get('walls', []): world += [(w_['x'], w_['y0']), (w_['x'], w_['y1'])]
    for c in spec.get('ceilings', []): world += [(c['x0'], c['y']), (c['x1'], c['y'])]
    for hgt in spec.get('heights', []): world += [(hgt['x'], hgt['from']), (hgt['x'], hgt['to'])]
    for s in spec.get('strings', []): world += [tuple(p) for p in s if _pt(p)]
    for s in spec.get('springs', []): world += [tuple(p) for p in (s.get('from'), s.get('to')) if _pt(p)]
    if _num(spec.get('base_to')) and track: world.append((track[0][0], spec['base_to']))
    if not world: world = [(0, 0), (1, 1)]
    xs = [q[0] for q in world]; ys = [q[1] for q in world]
    flat = (max(ys) - min(ys)) < (max(xs) - min(xs)) * .12            # 수평면만 있는 장면: 물체를 키우고 가운데로 모은다
    u = spec.get('scale', 1.6 if flat else 1.0)
    bw = box[2] - box[0]
    pad = spec.get('pad') or ((bw * .14, 90, bw * .14, 90) if flat else (min(110, bw * .13), 64, min(110, bw * .13), 66))
    if not spec.get('pad'):          # 높이 치수 글씨가 칸 밖으로 밀려 화살표에 겹치지 않게 여백을 넓힌다
        xs_min, xs_max = min(xs), max(xs)
        need = {'left': 0, 'right': 0}
        for hgt in spec.get('heights', []):
            if not hgt.get('label'): continue
            w_ = _width(hgt['label'], round(26 * TEXT)) + 30
            side = hgt.get('side', 'left')
            if side == 'left' and hgt['x'] - xs_min < (xs_max - xs_min) * .05: need['left'] = max(need['left'], w_)
            if side == 'right' and xs_max - hgt['x'] < (xs_max - xs_min) * .05: need['right'] = max(need['right'], w_)
        pad = (max(pad[0], need['left']), pad[1], max(pad[2], need['right']), pad[3])
    P = Fit(world, box, pad=pad)
    anchors = {}
    # 바닥·빗면·탁자
    if track:
        px = [P(p) for p in track]
        base = spec.get('base', 'solid')
        rr = 0 if spec.get('sharp') else spec.get('round', 40)
        if base == 'solid':
            bottom = P((0, spec['base_to']))[1] if _num(spec.get('base_to')) else max(y for _, y in px) + 26 * u
            region = _rounded(px, rr) + f'L{px[-1][0]:.1f},{bottom:.1f}L{px[0][0]:.1f},{bottom:.1f}Z'
            parts.append(f'<path d="{region}" fill="url(#{"tablefade" if _num(spec.get("base_to")) else "groundfade"})" stroke="none"/>')
            if _num(spec.get('base_to')):      # 탁자처럼 옆면이 있는 받침
                for q in (px[0], px[-1]):
                    if bottom - q[1] > 4: parts.append(_line(q, (q[0], bottom), 2.6))
        elif base == 'hatch':
            for a_, b_ in zip(px, px[1:]): parts.append(_hatch(a_, b_, side=-1))
        parts.append(_p(_rounded(px, rr), width=2.6))
        if _num(spec.get('datum')):          # 기준 수평 점선(바닥 음영 위에)
            y = P((0, spec['datum']))[1]
            parts.append(_line((px[0][0] - 10, y), (px[-1][0] + 10, y), width=1.6, dash='6 5'))
        if spec.get('ground_label'):        # "수평면": 바닥 오른쪽 끝 아래
            q = px[-1]; text = spec['ground_label']; lab = _lab(text, 0, 0, 24); wide = _text_width(text, lab['size'])
            labels.append({**lab, 'x': round(max(8, q[0] - wide - 4), 1), 'y': round(q[1] + 10, 1)})
    # 마찰 구간: 바닥 위에 굵은 회색 띠, 이름은 바닥 바깥쪽에
    for z in spec.get('zones', []):
        xs_ = [z['x0'] + (z['x1'] - z['x0']) * k / 24 for k in range(25)]
        band = [P((x, _track_at(track, x)[0])) for x in xs_]
        parts.append(_p(_poly(band), stroke='#9c9c9c', width=9))
        parts.append(_p(_poly(band), width=1.2))
        if z.get('label'):
            mx = (z['x0'] + z['x1']) / 2; yy, ang = _track_at(track, mx); c = P((mx, yy))
            nx_, ny_ = -math.sin(ang), -math.cos(ang)
            labels.append(_lab_side(z['label'], c[0] + nx_ * 26, c[1] + ny_ * 26, 'right' if nx_ >= -.05 else 'left', 24, 4))
    # 벽: 면은 굵은 선, 뒤쪽은 회색이 옅어지는 띠
    for w_ in spec.get('walls', []):
        a_, b_ = P((w_['x'], w_['y0'])), P((w_['x'], w_['y1']))
        side = 1 if w_.get('side', 'right') == 'right' else -1
        x0 = a_[0] if side > 0 else a_[0] - 24
        parts.append(f'<rect x="{x0:.1f}" y="{b_[1]:.1f}" width="24" height="{a_[1] - b_[1]:.1f}" fill="url(#{"wallfade" if side > 0 else "wallfadeL"})" stroke="none"/>')
        parts.append(_line(a_, b_, 3))
        if w_.get('label'): labels.append(_lab_side(w_['label'], a_[0] + side * 30, (a_[1] + b_[1]) / 2, 'right' if side > 0 else 'left', 24))
    for c in spec.get('ceilings', []):
        a_, b_ = P((c['x0'], c['y'])), P((c['x1'], c['y']))
        parts.append(_hatch(a_, b_, side=-1 if c.get('side', 'up') == 'up' else 1))

    # 물체 자리: 바닥 위(on) · 좌표(at)는 먼저, 도르래에 매단 것(hang)은 도르래 뒤에
    def size(o):
        kind = o.get('kind', 'block')
        return kind, o.get('w', (58 if kind == 'block' else 100) * u), o.get('h', (58 if kind == 'block' else 38) * u), o.get('r', 22 * u)

    def anchor_object(o, i, c, ang):
        kind, w, h, r = size(o)
        oid = o.get('id', o.get('label', f'O{i}'))
        corners = _box_corners(c, w, h, ang)
        if kind == 'ball':
            for name, (dx, dy) in {'left': (-1, 0), 'right': (1, 0), 'top': (0, -1), 'bottom': (0, 1)}.items():
                anchors[f'{oid}.{name}'] = (c[0] + dx * r, c[1] + dy * r)
        else:
            mid = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            anchors.update({f'{oid}.top': mid(corners[0], corners[1]), f'{oid}.right': mid(corners[1], corners[2]),
                            f'{oid}.bottom': mid(corners[2], corners[3]), f'{oid}.left': mid(corners[3], corners[0])})
        anchors[f'{oid}.center'] = c
        return (o, kind, c, ang, w, h, r, corners)
    placed = {}
    for i, o in enumerate(spec.get('objects', [])):
        kind, w, h, r = size(o)
        if 'on' in o:
            yy, ang = _track_at(track, o['on']); foot = P((o['on'], yy))
            lift = r if kind == 'ball' else (h / 2 + (14 * u if kind == 'cart' else 0))
            placed[i] = anchor_object(o, i, (foot[0] - math.sin(ang) * lift, foot[1] - math.cos(ang) * lift), ang)    # 바깥 법선 방향으로 띄운다
        elif _pt(o.get('at')):
            placed[i] = anchor_object(o, i, P(tuple(o['at'])), 0)
    pulleys = {}
    for i, pl in enumerate(spec.get('pulleys', [])):
        c = P(tuple(pl['at'])); r = pl.get('r', 24 * min(u, 1.2))
        if pl.get('align') and f"{pl['align']}.center" in anchors:      # 윗면 접점을 그 물체 중심 높이에 맞춘다(줄이 수평)
            c = (c[0], anchors[f"{pl['align']}.center"][1] + r)
        pid = pl.get('id', f'P{i}'); pulleys[pid] = (c, r)
        for name, (dx, dy) in {'left': (-1, 0), 'right': (1, 0), 'top': (0, -1), 'bottom': (0, 1)}.items():
            anchors[f'{pid}.{name}'] = (c[0] + dx * r, c[1] + dy * r)
    hung = []
    for i, o in enumerate(spec.get('objects', [])):
        if i in placed or o.get('hang') not in pulleys: continue
        c, r = pulleys[o['hang']]
        sx = 1 if o.get('side', 'right') == 'right' else -1
        placed[i] = anchor_object(o, i, (c[0] + sx * r, c[1] + o.get('drop', 3) * P.s), 0)
        hung.append((o['hang'], f"{o.get('id', o.get('label', f'O{i}'))}.top", sx))
    drawn = [placed[i] for i in sorted(placed)]

    def at(v):
        if isinstance(v, str):
            if v in pulleys: return v
            if v not in anchors: raise ValueError(f'기준점 {v}이(가) 없습니다(예: A.top, P0.left).')
            return anchors[v]
        return P(tuple(v))

    def string(path):
        pts = [at(q) for q in path]
        d = ''
        for k, q in enumerate(pts):
            if not isinstance(q, str):
                d += ('L' if d else 'M') + f'{q[0]:.1f},{q[1]:.1f}'; continue
            c, r = pulleys[q]
            prev = next((x for x in reversed(pts[:k]) if not isinstance(x, str)), None)
            nxt = next((x for x in pts[k + 1:] if not isinstance(x, str)), None)
            ends = [x for x in (prev, nxt) if x is not None]
            m = (sum(x[0] for x in ends) / len(ends), sum(x[1] for x in ends) / len(ends))
            L = math.dist(m, c) or 1; away = ((c[0] - m[0]) / L, (c[1] - m[1]) / L)       # 줄은 두 끝의 반대쪽으로 감긴다
            t1 = _tangent(c, r, prev, away) if prev else None
            t2 = _tangent(c, r, nxt, away) if nxt else None
            if t1: d += ('L' if d else 'M') + f'{t1[0]:.1f},{t1[1]:.1f}'
            if t1 and t2:
                cross = (t1[0] - c[0]) * (t2[1] - c[1]) - (t1[1] - c[1]) * (t2[0] - c[0])
                d += f'A{r:.1f},{r:.1f} 0 0 {1 if cross > 0 else 0} {t2[0]:.1f},{t2[1]:.1f}'
            elif t2: d += ('L' if d else 'M') + f'{t2[0]:.1f},{t2[1]:.1f}'
        return _p(d, width=2)
    strings = [list(s) for s in spec.get('strings', [])]
    for pid, top, sx in hung:
        host = next((s for s in strings if s and s[-1] == pid), None)
        if host: host.append(top)
        else:
            c, r = pulleys[pid]; parts.append(_line((c[0] + sx * r, c[1]), anchors[top], 2))
    for s in strings: parts.append(string(s))
    for s in spec.get('springs', []):
        a_, b_ = at(s['from']), at(s['to'])
        if s.get('level', True):            # 한쪽이 물체면 그 높이에 맞춰 수평으로
            if isinstance(s['to'], str) and not isinstance(s['from'], str): a_ = (a_[0], b_[1])
            elif isinstance(s['from'], str) and not isinstance(s['to'], str): b_ = (b_[0], a_[1])
        parts.append(_spring(a_, b_, s.get('coils'), 17 * min(u, 1.3)))
    # 도르래(줄 위에 그린다)
    for i, pl in enumerate(spec.get('pulleys', [])):
        pid = pl.get('id', f'P{i}'); c, r = pulleys[pid]
        mount = pl.get('mount', 'up')
        if mount == 'corner' and track:     # 탁자 모서리에 고정하는 받침
            parts.append(_line(c, P(track[-1]), 3.2))
        elif mount in ('up', 'down', 'left', 'right'):
            dx, dy = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}[mount]
            end = (c[0] + dx * (r + 30), c[1] + dy * (r + 30))
            parts.append(_line(c, end, 3))
            if not spec.get('ceilings'):
                a_ = (end[0] - dy * 26, end[1] - dx * 26); b_ = (end[0] + dy * 26, end[1] + dx * 26)
                parts.append(_hatch(a_, b_, side=1 if mount in ('up', 'left') else -1, size=8, step=10))
        parts.append(_circle(c, r, 'white', 2.5)); parts.append(_circle(c, 4.5, LINE, 1))
    for o, kind, c, ang, w, h, r, corners in drawn:
        dash = '7 5' if o.get('ghost') else ''
        fill = {'gray': '#bdbdbd', 'light': PALE}.get(o.get('shade'), 'white')
        if kind == 'ball':
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
            parts.append(f'<circle cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="{r:.1f}" fill="{"white" if o.get("ghost") else "url(#ball)"}" stroke="{LINE}" stroke-width="2.2"{dash_attr}/>')
            if o.get('label'):
                labels.append(_lab(o['label'], c[0], c[1], max(22, round(r * 1.2)), scaled=True) if r >= 19 else _lab_side(o['label'], c[0] + r * .6, c[1] - r * .9, 'right', 24, 4))
            continue
        parts.append(_p(_poly(corners, True), fill=fill, width=2.4, dash=dash))
        if kind == 'cart':
            ca, sa = math.cos(ang), math.sin(ang)
            for k in (-.3, .3):
                wx = c[0] + k * w * ca + (h / 2 + 4 * u) * sa; wy = c[1] - k * w * sa + (h / 2 + 4 * u) * ca
                parts.append(_circle((wx, wy), 10 * u, 'white', 2.2)); parts.append(_circle((wx, wy), 2.5 * u, LINE, 1))
        if o.get('label'): labels.append(_lab(o['label'], c[0], c[1], round(min(h * .62, 40)), scaled=True))
        if o.get('mass'): labels.append(_lab_side(o['mass'], c[0], min(q[1] for q in corners), 'up', 24, 6))
    # 화살표(힘·속도)
    for a in spec.get('arrows', []):
        start = at(a['from'])
        if 'to' in a: end = at(a['to'])
        else:
            ang = math.radians(a.get('dir', 0)); L = a.get('len', 90) * min(u, 1.3)
            end = (start[0] + L * math.cos(ang), start[1] - L * math.sin(ang))
        parts.append(_arrow(start, end, width=2.4, head=14))
        if a.get('label'):
            ang = math.atan2(end[1] - start[1], end[0] - start[0])
            side = a.get('side') or ('up' if abs(math.cos(ang)) > .7 else ('right' if math.cos(ang) >= 0 else 'left'))
            mx, my = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2) if side in ('up', 'down') else end
            labels.append(_lab_side(a['label'], mx, my - (4 if side == 'up' else 0), side, 26, 6))
    # 높이·길이 치수
    for hgt in spec.get('heights', []):
        a_, b_ = P((hgt['x'], hgt['from'])), P((hgt['x'], hgt['to']))
        m = ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2)
        parts.append(_arrow(m, a_, 1.8, 11) + _arrow(m, b_, 1.8, 11))
        for q in (a_, b_): parts.append(_line((q[0] - 9, q[1]), (q[0] + 9, q[1]), 1.6))
        for key, q, yv in (('x_from', a_, hgt['from']), ('x_to', b_, hgt['to'])):
            if _num(hgt.get(key)): parts.append(_line(q, P((hgt[key], yv)), 1.4, '5 4'))
        if hgt.get('label'):
            labels.append(_lab_side(hgt['label'], a_[0], m[1], hgt.get('side', 'left'), 26, 8))
    for ln in spec.get('lengths', []):
        a_, b_ = at(ln['from']), at(ln['to']); off = ln.get('offset', 0)
        L = math.dist(a_, b_); nx, ny = -(b_[1] - a_[1]) / L, (b_[0] - a_[0]) / L
        a2, b2 = (a_[0] + nx * off, a_[1] + ny * off), (b_[0] + nx * off, b_[1] + ny * off)
        if off:
            s_ = 1 if off > 0 else -1
            parts.append(_line(a_, (a2[0] + nx * 8 * s_, a2[1] + ny * 8 * s_), 1.2)); parts.append(_line(b_, (b2[0] + nx * 8 * s_, b2[1] + ny * 8 * s_), 1.2))
        m = ((a2[0] + b2[0]) / 2, (a2[1] + b2[1]) / 2)
        parts.append(_arrow(m, a2, 1.8, 11) + _arrow(m, b2, 1.8, 11))
        if ln.get('label'):
            s_ = 1 if off >= 0 else -1
            labels.append(_lab(ln['label'], m[0] + nx * 30 * s_, m[1] + ny * 30 * s_, 26))
    # 각: 빗면과 수평 사이
    for an in spec.get('angles', []):
        i = an['at']; v = P(track[i]); nbrs = [P(track[j]) for j in (i - 1, i + 1) if 0 <= j < len(track)]
        hi = min(nbrs, key=lambda q: q[1])
        a1 = math.atan2(hi[1] - v[1], hi[0] - v[0]); a0 = 0 if hi[0] >= v[0] else math.pi
        rr = an.get('r', 50)
        s0, e0 = (v[0] + rr * math.cos(a0), v[1] + rr * math.sin(a0)), (v[0] + rr * math.cos(a1), v[1] + rr * math.sin(a1))
        sweep = 1 if (a1 - a0) % (2 * math.pi) < math.pi else 0
        parts.append(_line(v, (v[0] + (rr + 30) * math.cos(a0), v[1]), 1.4, '5 4'))
        parts.append(_p(f'M{s0[0]:.1f},{s0[1]:.1f}A{rr},{rr} 0 0 {sweep} {e0[0]:.1f},{e0[1]:.1f}', width=1.8))
        mid = math.atan2(math.sin(a0) + math.sin(a1), math.cos(a0) + math.cos(a1))
        if an.get('label'): labels.append(_lab(an['label'], v[0] + (rr + 26) * math.cos(mid), v[1] + (rr + 20) * math.sin(mid), 24))
    # 점과 글씨
    for pt in spec.get('points', []):
        c = P((pt['x'], _track_at(track, pt['x'])[0])) if 'x' in pt and track else at(pt['at'])
        parts.append(f'<circle cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="5" fill="{LINE}"/>')
        if pt.get('label'): labels.append(_lab_side(pt['label'], c[0], c[1] - 4, pt.get('side', 'up'), 24, 6))
    for t in spec.get('texts', []):
        c = at(t['at'])
        labels.append(_lab_side(t['text'], c[0], c[1], t['side'], t.get('size', 24), t.get('gap', 8)) if t.get('side') else _lab(t['text'], c[0], c[1], t.get('size', 24)))


# ---------------------------------------------------------------- 회로
PARTS = ('wire', 'resistor', 'battery', 'switch', 'bulb', 'ammeter', 'voltmeter', 'led', 'diode', 'capacitor', 'ac', 'coil')


def _check_circuit(spec):
    nodes = spec.get('nodes')
    if not isinstance(nodes, dict) or not nodes or not all(_pt(v) for v in nodes.values()):
        return ['회로는 nodes: {"a":[0,0],"b":[0,4],…}(마디 이름과 좌표)가 필요합니다.']
    out = []
    if not _need(spec, 'parts'): out.append('회로는 parts: [{"kind":"resistor","from":"a","to":"b"},…]가 필요합니다.')
    for p in spec.get('parts', []):
        if p.get('kind') not in PARTS: out.append('부품 kind는 ' + ', '.join(PARTS) + ' 중 하나입니다.')
        if p.get('from') not in nodes or p.get('to') not in nodes: out.append(f"부품 {p.get('kind')}의 from/to 마디를 확인해 주세요.")
        elif nodes[p['from']] == nodes[p['to']]: out.append('부품의 두 마디가 같은 자리입니다.')
    return out


def _component(kind, a, b, p, parts, labels, centroid, others=()):
    L = math.dist(a, b); ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L; nx, ny = -uy, ux
    m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    pt = lambda t, s=0: (m[0] + ux * t + nx * s, m[1] + uy * t + ny * s)
    out = 1 if (m[0] - centroid[0]) * nx + (m[1] - centroid[1]) * ny >= 0 else -1      # 회로 바깥쪽(글씨 쪽)
    room = {1: 1e9, -1: 1e9}           # 안쪽 가지면 양옆 중 빈 곳이 넓은 쪽에 글씨를 둔다
    for q in others:
        along = (q[0] - m[0]) * ux + (q[1] - m[1]) * uy; side_ = (q[0] - m[0]) * nx + (q[1] - m[1]) * ny
        if abs(along) <= L / 2 + 1 and abs(side_) > 1: room[1 if side_ > 0 else -1] = min(room[1 if side_ > 0 else -1], abs(side_))
    if min(room.values()) < 1e9 and room[out] < room[-out] - 1: out = -out
    if p.get('side') == 'in': out = -out
    half = {'wire': 0, 'resistor': 38, 'battery': 9, 'switch': 30, 'bulb': 22, 'ammeter': 22, 'voltmeter': 22,
            'led': 20, 'diode': 18, 'capacitor': 8, 'ac': 22, 'coil': 40}[kind]
    half = min(half, L / 2 - 4)
    if kind == 'wire':
        parts.append(_line(a, b, 2.4)); seg = 0
    else:
        parts.append(_line(a, pt(-half), 2.4)); parts.append(_line(pt(half), b, 2.4))
    if kind == 'resistor':
        if p.get('style') == 'box':
            parts.append(_p(_poly([pt(-half, -11), pt(half, -11), pt(half, 11), pt(-half, 11)], True), fill='white', width=2.4))
        else:
            zz = [pt(-half)] + [pt(-half + (2 * half) * (k + .5) / 6, 11 if k % 2 == 0 else -11) for k in range(6)] + [pt(half)]
            parts.append(_p(_poly(zz), width=2.4))
    elif kind == 'battery':      # 긴 판이 (+), to 쪽
        parts.append(_line(pt(half, -24), pt(half, 24), 2.6))
        parts.append(_line(pt(-half, -12), pt(-half, 12), 6))
    elif kind == 'capacitor':
        for t in (-half, half): parts.append(_line(pt(t, -22), pt(t, 22), 2.8))
    elif kind == 'switch':
        parts.append(_circle(pt(-half), 4.5, 'white', 2)); parts.append(_circle(pt(half), 4.5, 'white', 2))
        tip = pt(half - 4, 0) if p.get('state') == 'closed' else pt(half * .55, -out * 2 * half * .55)     # 열린 스위치는 회로 안쪽으로 든다
        parts.append(_line(pt(-half + 4), tip, 2.4))
    elif kind in ('bulb', 'ammeter', 'voltmeter', 'ac'):
        parts.append(_circle(m, half, 'white', 2.4))
        if kind == 'bulb':
            d = half * .7071
            parts.append(_line((m[0] - d, m[1] - d), (m[0] + d, m[1] + d), 2)); parts.append(_line((m[0] - d, m[1] + d), (m[0] + d, m[1] - d), 2))
        elif kind == 'ac':
            wave = [pt(-12 + 24 * k / 16, -8 * math.sin(2 * math.pi * k / 16)) for k in range(17)]
            parts.append(_p(_poly(wave), width=2))
        else:
            labels.append(_lab('A' if kind == 'ammeter' else 'V', m[0], m[1] - 5, 26, scaled=True))        # 직류 계기: 글자 밑에 짧은 선
            parts.append(_line((m[0] - 9, m[1] + 11), (m[0] + 9, m[1] + 11), 2))
    elif kind in ('led', 'diode'):     # 삼각형이 to 쪽을 향한다(순방향)
        tri = [pt(-half, -15), pt(-half, 15), pt(half * .6, 0)]
        parts.append(_p(_poly(tri, True), fill='white', width=2.4))
        parts.append(_line(pt(half * .6, -15), pt(half * .6, 15), 2.6)); parts.append(_line(pt(half * .6), pt(half), 2.4))
        if kind == 'led':
            for k in (0, 10):        # 빛 화살표는 글씨 반대쪽
                s0 = pt(-2 + k, -out * 18); s1 = pt(8 + k, -out * 32)
                parts.append(_arrow(s0, s1, 1.6, 8))
    elif kind == 'coil':
        loops = 5; d = ''
        for k in range(loops):
            s = pt(-half + 2 * half * k / loops); e = pt(-half + 2 * half * (k + 1) / loops)
            d += f'M{s[0]:.1f},{s[1]:.1f}A{half / loops:.1f},{half / loops:.1f} 0 0 1 {e[0]:.1f},{e[1]:.1f}'
        parts.append(_p(d, width=2.4))
    if p.get('label'):
        gap = {'battery': 30, 'capacitor': 28, 'switch': 26}.get(kind, half * .2 + 22 if kind not in ('wire',) else 18)
        c = (m[0] + nx * out * (gap + 6), m[1] + ny * out * (gap + 6))
        horiz = abs(ux) > .7
        side = ('down' if ny * out > 0 else 'up') if horiz else ('right' if nx * out > 0 else 'left')
        labels.append(_lab_side(p['label'], c[0] - nx * out * 10, c[1] - ny * out * 10, side, 24, 4))


def _circuit(spec, parts, labels, box=FRAME):
    nodes = {k: tuple(v) for k, v in spec['nodes'].items()}
    bw = box[2] - box[0]
    fit = Fit(list(nodes.values()), box, pad=spec.get('pad', (min(140, bw * .26), 70, min(140, bw * .26), 70)))
    px = {k: fit(v) for k, v in nodes.items()}
    cx = sum(p[0] for p in px.values()) / len(px); cy = sum(p[1] for p in px.values()) / len(px)
    degree = {k: 0 for k in nodes}
    for p in spec['parts']:
        _component(p['kind'], px[p['from']], px[p['to']], p, parts, labels, (cx, cy), list(px.values()))
        degree[p['from']] += 1; degree[p['to']] += 1
    for k, d in degree.items():
        if d >= 3: parts.append(f'<circle cx="{px[k][0]:.1f}" cy="{px[k][1]:.1f}" r="5.5" fill="{LINE}"/>')
    for t in spec.get('terminals', []):
        name = t if isinstance(t, str) else t.get('node'); text = t.get('label', name) if isinstance(t, dict) else name
        c = px[name]; parts.append(_circle(c, 6, 'white', 2))
        side = 'right' if c[0] >= cx else 'left'
        labels.append(_lab_side(text, c[0], c[1], side, 24, 8))
    for n in spec.get('node_labels', []):
        c = px[n['node']]; labels.append(_lab_side(n['label'], c[0], c[1], n.get('side', 'up'), 24, 8))
    return max(q[1] for q in px.values()) + 40


# ---------------------------------------------------------------- 그래프
def _check_graph(spec):
    out = []
    if not _need(spec, 'curves'): out.append('그래프는 curves: [{"points":[[0,0],[1,2],…]}] 또는 [{"pulse":{…}}]가 필요합니다.')
    for c in spec.get('curves', []):
        if isinstance(c.get('pulse'), dict):
            q = c['pulse']
            if not (_num(q.get('x1')) and _num(q.get('peak')) and q['x1'] > q.get('x0', 0)): out.append('pulse는 {"x0":0,"x1":2,"peak":3,"at":0.4}처럼 씁니다.')
            continue
        pts = c.get('points', [])
        if len(pts) < 2 or not all(_pt(p) for p in pts): out.append('곡선의 points는 [x,y] 2개 이상입니다.')
    return out


def _monotone(pts):
    """x가 커지는 점열을 넘치지 않는 매끄러운 곡선으로(Fritsch–Carlson)."""
    n = len(pts)
    if n < 3: return list(pts)
    dx = [pts[i + 1][0] - pts[i][0] for i in range(n - 1)]
    if any(d <= 0 for d in dx): return list(pts)
    sl = [(pts[i + 1][1] - pts[i][1]) / dx[i] for i in range(n - 1)]
    m = [sl[0]] + [0 if sl[i - 1] * sl[i] <= 0 else (sl[i - 1] + sl[i]) / 2 for i in range(1, n - 1)] + [sl[-1]]
    for i in range(n - 1):
        if sl[i] == 0: m[i] = m[i + 1] = 0; continue
        a, b = m[i] / sl[i], m[i + 1] / sl[i]
        if a * a + b * b > 9:
            t = 3 / math.sqrt(a * a + b * b); m[i] = t * a * sl[i]; m[i + 1] = t * b * sl[i]
    out = [pts[0]]
    for i in range(n - 1):          # 에르미트 곡선을 촘촘한 점으로(넓이 칠하기와 같은 선을 쓰려고)
        for k in range(1, 21):
            t = k / 20; h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
            out.append((pts[i][0] + dx[i] * t, h00 * pts[i][1] + h10 * dx[i] * m[i] + h01 * pts[i + 1][1] + h11 * dx[i] * m[i + 1]))
    return out


def _pulse(p):
    """종 모양 펄스: x0에서 x1까지, 높이 peak, 꼭대기는 at(0~1, 기본 0.4). 양 끝은 기울기 0."""
    x0, x1, peak = p.get('x0', 0), p['x1'], p['peak']
    at = min(.8, max(.2, p.get('at', .4))); total = p.get('sharp', 4.2)
    al, be = total * at, total * (1 - at)
    top = at ** al * (1 - at) ** be
    return [(x0 + (x1 - x0) * k / 80, peak * ((k / 80) ** al * (1 - k / 80) ** be) / top) for k in range(81)]


def _graph(spec, parts, labels, box=FRAME):
    for c in spec['curves']:
        if c.get('pulse'): c['points'] = _pulse(c['pulse'])
    xs = [p[0] for c in spec['curves'] for p in c['points']] + [0]
    ys = [p[1] for c in spec['curves'] for p in c['points']] + [0]
    ax, ay = spec.get('x') or {}, spec.get('y') or {}
    x0, x1 = min(ax.get('min', min(xs)), 0), ax.get('max', max(xs) * 1.12)
    y0, y1 = min(ay.get('min', min(ys)), 0), ay.get('max', max(ys) * 1.15)
    L, T, R, B = box[0] + 100, box[1] + 60, box[2] - 140, box[3] - 70
    X = lambda v: L + (v - x0) / (x1 - x0) * (R - L)
    Y = lambda v: B - (v - y0) / (y1 - y0) * (B - T)
    ox, oy = X(0), Y(0)
    lines = []
    for c in spec['curves']:
        if c.get('pulse'):
            c['points'] = _pulse(c['pulse'])
        pts = [(X(x), Y(y)) for x, y in c['points']]
        lines.append(_monotone(pts) if c.get('smooth') else pts)
    for f in spec.get('fills', []):      # 곡선 아래 넓이(충격량·이동 거리)
        line = lines[f.get('curve', 0)]; a_, b_ = X(f['x0']), X(f['x1'])
        seg = [q for q in line if a_ - .5 <= q[0] <= b_ + .5]
        pts = [(a_, oy)] + seg + [(b_, oy)]
        parts.append(f'<path d="{_poly(pts, True)}" fill="{LIGHT}" stroke="none"/>')
    for g in spec.get('guides', []):     # 점에서 두 축으로 점선
        gx, gy = X(g[0]), Y(g[1])
        parts.append(_line((gx, gy), (gx, oy), 1.4, '5 4')); parts.append(_line((gx, gy), (ox, gy), 1.4, '5 4'))
    parts.append(_arrow((X(x0), oy), (R + 40, oy), 2.2, 13)); parts.append(_arrow((ox, Y(y0)), (ox, T - 30), 2.2, 13))
    labels.append(_lab_side(ax.get('label', ''), R + 46, oy, 'right', 24, 4)) if ax.get('label') else None
    labels.append(_lab_side(ay.get('label', ''), ox - 8, T - 24, 'left', 24, 4)) if ay.get('label') else None
    labels.append(_lab_side(spec.get('origin', '0'), ox - 4, oy + 4, 'left', 24, 6)) if spec.get('origin', '0') != '' else None
    for v, text in ax.get('ticks', []):
        parts.append(_line((X(v), oy), (X(v), oy - 8), 1.8)); labels.append(_lab_side(text, X(v), oy + 4, 'down', 24, 6))
    for v, text in ay.get('ticks', []):
        parts.append(_line((ox, Y(v)), (ox + 8, Y(v)), 1.8)); labels.append(_lab_side(text, ox - 6, Y(v), 'left', 24, 8))
    for c, line in zip(spec['curves'], lines):
        pts = [(X(x), Y(y)) for x, y in c['points']]
        parts.append(_p(_poly(line), width=2.8, dash='9 6' if c.get('dash') else ''))
        if c.get('label'):
            k = c.get('label_at', len(pts) // 2); k = max(0, min(len(pts) - 1, k))
            labels.append(_lab_side(c['label'], pts[k][0] + 6, pts[k][1] - 6, c.get('label_side', 'up'), 26, 8))
    for pt in spec.get('points', []):
        parts.append(f'<circle cx="{X(pt[0]):.1f}" cy="{Y(pt[1]):.1f}" r="5" fill="{LINE}"/>')


# ---------------------------------------------------------------- 여러 칸
PANEL_TYPES = {'mechanics': _mechanics, 'circuit': _circuit, 'graph': _graph}
PANEL_CHECK = {'mechanics': _check_mechanics, 'circuit': _check_circuit, 'graph': _check_graph}


def _check_panels(spec):
    items = spec.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 3: return ['panels는 items(1~3칸)가 필요합니다.']
    out = []
    for it in items:
        if it.get('type') not in PANEL_TYPES: out.append('칸의 type은 mechanics, circuit, graph 중 하나입니다.'); continue
        out += PANEL_CHECK[it['type']](it)
    return out


def _panels(spec, parts, labels):
    items = spec['items']; n = len(items)
    row = spec.get('layout', 'row') == 'row'
    weights = [it.get('weight', 1) for it in items]; total = sum(weights); pos = 0
    for it, wgt in zip(items, weights):
        if row: box = (W * pos / total, 0, W * (pos + wgt) / total, H - 40)
        else: box = (0, (H - 10) * pos / total, W, (H - 10) * (pos + wgt) / total - 34)
        pos += wgt
        bottom = PANEL_TYPES[it['type']](it, parts, labels, box)
        y = min(box[3] + 14, bottom + 30) if isinstance(bottom, (int, float)) else box[3] + 14
        if it.get('caption'): labels.append(_lab(it['caption'], (box[0] + box[2]) / 2, y, 26))


CHECK = {'mechanics': _check_mechanics, 'circuit': _check_circuit, 'graph': _check_graph, 'panels': _check_panels}
RENDER = {'mechanics': _mechanics, 'circuit': _circuit, 'graph': _graph, 'panels': _panels}

PROMPT = """
물리 도식(앱이 그림): 역학 상황, 회로, 그래프, 그리고 이들을 (가)(나)로 나란히 놓는 panels. 좌표는 세계 좌표(y가 위로 커짐)이고 앱이 칸에 맞춰 늘이고 줄인다. 물체·도르래·부품 크기는 앱이 정한다. 글씨는 수식이면 $...$(LaTeX), 한글이면 평문이다.
- 역학 상황: {"type":"mechanics","track":[[0,4],[3,1],[8,1]],"base":"solid|line|hatch","datum":0,"objects":[{"kind":"block|ball|cart","on":0.8,"label":"A","mass":"$2m$","ghost":false},{"kind":"block","at":[x,y],"label":"B"}],"walls":[{"x":8,"y0":1,"y1":2.2,"side":"right","label":"벽"}],"zones":[{"x0":1,"x1":2,"label":"마찰 구간"}],"heights":[{"x":-0.5,"from":1,"to":4,"label":"$3h$","x_to":0}],"lengths":[{"from":[3,1],"to":[8,1],"label":"$L$","offset":-30}],"angles":[{"at":1,"label":"$30^{\\\\circ}$"}],"points":[{"x":5,"label":"p"}],"arrows":[{"from":"A.right","dir":0,"len":90,"label":"$F$"}],"pulleys":[{"at":[x,y],"mount":"up"}],"ceilings":[{"x0":..,"x1":..,"y":..}],"strings":[["A.top","P0.left"]],"springs":[{"from":[x,y],"to":"A.left"}],"texts":[{"at":[x,y],"text":"수평면"}]} track의 x는 왼쪽부터 커진다. 기울기는 마찰 구간이나 점에서 바꾸지 말고 문항의 상황대로만 꺾는다(꺾이는 곳은 앱이 둥글게, round로 반지름 조절). 출발하는 물체는 공중에 띄우지 말고 on으로 바닥 위에 놓는다. on은 바닥 위 x 위치(빗면이면 물체가 기울어 놓인다). 기준점은 물체 이름.top/bottom/left/right/center, 도르래 P0.left 등. dir는 도(오른쪽 0, 위 90). 값이 문항 조건(높이 비, 각)과 맞게 쓴다.
- 회로: {"type":"circuit","nodes":{"a":[0,0],"b":[0,3],"c":[4,3],"d":[4,0]},"parts":[{"kind":"battery","from":"a","to":"b","label":"$12\\\\,\\\\mathrm{V}$"},{"kind":"resistor","from":"b","to":"c","label":"$3\\\\,\\\\Omega$"},{"kind":"wire","from":"c","to":"d"},…]} kind: wire, resistor, battery(긴 판 (+)이 to 쪽), switch(state open|closed), bulb, ammeter, voltmeter, led·diode(to 쪽이 순방향), capacitor, ac, coil. 갈림점 점은 앱이 찍는다. terminals:["a"]는 단자.
- 그래프: {"type":"graph","x":{"label":"시간","ticks":[[1,"$t_{0}$"],[2,"$2t_{0}$"]]},"y":{"label":"속력","ticks":[[2,"$v_{0}$"]]},"curves":[{"points":[[0,3],[1,2],[2,0]],"smooth":true,"label":"A"}],"guides":[[1,2]],"fills":[{"curve":0,"x0":0,"x1":1}]} 점선 guides는 그 점에서 두 축으로 내린다. smooth는 점을 지나는 매끄러운 곡선. 힘-시간처럼 0에서 부드럽게 올라갔다 내려오는 곡선은 {"pulse":{"x0":0,"x1":1,"peak":3,"at":0.4},"label":"A"}로 쓴다(at은 꼭대기 위치 비율).
- 여러 칸: {"type":"panels","layout":"row|column","items":[{"type":"mechanics",…,"caption":"(가)"},{"type":"graph",…,"caption":"(나)"}]}
"""
