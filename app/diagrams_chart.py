"""수치 자료 그래프: 막대 · 꺾은선 · 원 · 띠 · 산점. 평가원 사회·과학탐구 그래프 꼴(흑백, 회색 단계와 빗금으로 계열 구분).

값은 AI가 쓴 수 그대로 앱이 눈금에 맞춰 그린다(손으로 그린 SVG처럼 막대 높이가 어긋나지 않는다).
글씨(눈금 수, 항목 이름, 범례, 값)는 글씨 레이어로 따로 둔다. 표가 더 맞는 자료는 이 도식을 쓰지 않는다.
"""
import math
import re

from .diagrams import LINE, W, H, _p, _line, _need, _text_width
from .maps import _label

FRAME = (0, 0, W, H)
# 글씨 규칙(instructions/그래프-자료-지침.md): 그래프 안 글씨는 본문 명조 하나, 크기는 두 단계뿐이다.
# 그림 1000 px가 시험지에서 약 10 cm(1 px ≈ 0.29 pt)이므로 MAIN 26 px ≈ 7.5 pt(본문 10 pt의 3/4), SMALL 22 px ≈ 6.4 pt.
MAIN = 26        # 눈금 수, 축 이름·단위, 항목 이름, 범례, 제목, (가)(나)
SMALL = 22       # 막대·점 위의 값, 띠 안의 수, 각주·출처
KINDS = ('bar', 'line', 'pie', 'band', 'scatter')
BAR_FILLS = ('#bdbdbd', LINE, 'white', 'hatch', '#6f6f6f')
BAND_FILLS = ('white', '#d2d2d2', 'hatch', '#9c9c9c', 'cross', '#efefef', 'hatch2', '#7a7a7a')
PIE_FILLS = ('white', '#dedede', '#bababa', '#969696', '#f2f2f2', '#cccccc')
MARKERS = ('dot', 'circle', 'square', 'triangle', 'diamond')


# ---------------------------------------------------------------- 공통
def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _fmt(v):
    v = float(v)
    return str(int(round(v))) if abs(v - round(v)) < 1e-9 else f'{v:g}'


def _size(box):
    """그래프 글씨 크기는 칸이 좁아도 바꾸지 않는다(평가원: 그래프가 작아질 뿐 글씨 크기는 같다)."""
    return MAIN


def _text(text, x, y, size, align='center'):
    """글씨 하나. align은 기준점 x에 글씨의 가운데·오른쪽 끝·왼쪽 끝을 맞춘다."""
    text = str(text)
    wide = _text_width(re.sub(r'\$|\\[A-Za-z]+|[{}_^]', '', text), size)        # $t_{1}$은 글씨 둘 정도의 폭
    cx = {'center': x, 'right': x - wide / 2, 'left': x + wide / 2}[align]
    # maps._label은 $를 지워 평문으로 만든다. 그래프는 $X$를 수식 글씨로 남겨 _fonts_safe가 나눈다.
    return {'kind': 'korean', 'text': text, 'x': round(max(12, min(W - wide - 14, cx - wide / 2)), 1),
            'y': round(max(12, min(H - size - 16, y - size / 2)), 1), 'size': size, 'rotation': 0}


GAP = 30          # 물결로 자른 구간이 차지하는 높이(px)


def _ymap(lo, hi, T, B, axis):
    """세로축 값 → 화면 y. axis.break=[a,b]면 a~b를 짧은 틈으로 접는다(평가원 꼴의 물결 자르기, 2026-11-13 교사 요청).
    눈금 범위가 커서 아래쪽 눈금이 붙을 때 쓴다. 곡선은 틈을 지나며 끊기지 않는다."""
    brk = (axis or {}).get('break')
    if not (isinstance(brk, list) and len(brk) == 2 and _num(brk[0]) and _num(brk[1]) and lo < brk[0] < brk[1] < hi):
        return (lambda v: B - (v - lo) / (hi - lo) * (B - T)), None
    a, b = brk; span = (a - lo) + (hi - b); H = B - T - GAP
    def Y(v):
        if v <= a: return B - (v - lo) / span * H
        if v >= b: return B - ((a - lo) + (v - b)) / span * H - GAP
        return B - (a - lo) / span * H - (v - a) / (b - a) * GAP
    return Y, (Y(a), Y(b))


def _split_at(run, brk):
    """[(x, 값)…] 꺾은선을 자를 값 a, b를 지나는 곳에서 나눈다. 자른 띠 양쪽의 선이 실제 기울기 그대로 띠 가장자리에 닿게."""
    if not brk: return run
    out = []
    for (x0, v0), (x1, v1) in zip(run, run[1:]):
        out.append((x0, v0))
        cuts = [c for c in brk if min(v0, v1) < c < max(v0, v1)]
        for c in sorted(cuts, key=lambda c: (c - v0) / (v1 - v0)):
            t = (c - v0) / (v1 - v0); out.append((x0 + (x1 - x0) * t, c))
    if run: out.append(run[-1])
    return out


def _cut_band(parts, gap, x0, x1):
    """그래프 전체를 실제로 자른다: 자른 띠(축·선·막대 모두)를 흰색으로 지우고 위아래 가장자리를 물결로 그린다(2026-11-13 교사 지적)."""
    ya, yb = gap
    wave = lambda y, k: f'{x0 + k * 2:.1f},{y + 3 * math.sin(k * math.pi / 6):.1f}'      # 한 물결 24px, 부드럽게
    n = max(2, int((x1 - x0) / 2))
    top = [wave(yb, k) for k in range(n + 1)]; bottom = [wave(ya, k) for k in range(n, -1, -1)]
    parts.append(f'<path d="M{" L".join(top + bottom)} Z" fill="white" stroke="none"/>')
    for y in (yb, ya): parts.append(_p('M' + ' L'.join(wave(y, k) for k in range(n + 1)), width=1.8))


def _nice_step(span):
    raw = span / 5 if span > 0 else 1
    mag = 10 ** math.floor(math.log10(raw))
    return next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw - 1e-12)


def _scale(values, axis):
    """눈금: 교사가 min·max·step을 주면 그대로, 아니면 0을 포함하는 보기 좋은 눈금."""
    axis = axis or {}
    vals = [v for v in values if _num(v)] or [0]
    lo = axis.get('min', min(0, min(vals)))
    hi = axis.get('max', max(vals))
    if hi <= lo: hi = lo + 1
    step = axis.get('step') or _nice_step(hi - lo)
    if 'max' not in axis: hi = math.ceil(hi / step - 1e-9) * step
    if 'min' not in axis and lo < 0: lo = math.floor(lo / step + 1e-9) * step
    n = max(1, round((hi - lo) / step))
    return lo, lo + n * step, [lo + i * step for i in range(n + 1)]


def _ticks(axis, auto):
    """눈금: ticks:false면 숨기고, [값,…]이나 [[값,"글씨"],…]면 그 값만, 아니면 자동 눈금."""
    t = (axis or {}).get('ticks', True)
    if t is False: return []
    if isinstance(t, list):
        out = []
        for v in t:
            if isinstance(v, list) and len(v) == 2 and _num(v[0]): out.append((v[0], str(v[1])))
            elif _num(v): out.append((v, _fmt(v)))
        return out
    return [(v, _fmt(v)) for v in auto]


def _hatch(x0, y0, x1, y1, gap=9, flip=False):
    """사각형 안의 빗금(SVG pattern은 시험지 변환에서 쓰지 않는다)."""
    out = []
    if x1 - x0 < 2 or y1 - y0 < 2: return ''
    k = x0 + y0 + gap / 2
    while k < x1 + y1:
        a, b = max(x0, k - y1), min(x1, k - y0)
        if b > a:
            p, q = (a, k - a), (b, k - b)
            if flip: p, q = (x0 + x1 - p[0], p[1]), (x0 + x1 - q[0], q[1])
            out.append(f'M{p[0]:.1f},{p[1]:.1f}L{q[0]:.1f},{q[1]:.1f}')
        k += gap
    return _p(''.join(out), width=1.3) if out else ''


def _rect(x0, y0, x1, y1, fill, width=2):
    x0, x1 = min(x0, x1), max(x0, x1); y0, y1 = min(y0, y1), max(y0, y1)
    base = 'white' if fill.startswith('hatch') or fill == 'cross' else fill
    out = f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" fill="{base}" stroke="none"/>'
    if fill.startswith('hatch') or fill == 'cross': out += _hatch(x0, y0, x1, y1, flip=fill == 'hatch2')
    if fill == 'cross': out += _hatch(x0, y0, x1, y1, flip=True)
    return out + f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" fill="none" stroke="{LINE}" stroke-width="{width}"/>'


def _marker(kind, x, y, r=7):
    if kind == 'dot': return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{LINE}" stroke="none"/>'
    if kind == 'circle': return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="white" stroke="{LINE}" stroke-width="2.2"/>'
    if kind == 'square': return f'<rect x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r}" height="{2 * r}" fill="{LINE}" stroke="none"/>'
    if kind == 'triangle':
        h = r * 1.25
        return f'<polygon points="{x:.1f},{y - h:.1f} {x - h:.1f},{y + h * .75:.1f} {x + h:.1f},{y + h * .75:.1f}" fill="white" stroke="{LINE}" stroke-width="2.2"/>'
    h = r * 1.3
    return f'<polygon points="{x:.1f},{y - h:.1f} {x + h:.1f},{y:.1f} {x:.1f},{y + h:.1f} {x - h:.1f},{y:.1f}" fill="{LINE}" stroke="none"/>'


def _legend(items, box, parts, labels, size, spec=None):
    """범례 한 줄을 그림 위쪽 가운데에. items: (모양, 값, 이름).
    (가)(나) 칸들이 같은 범례를 쓰면 첫 칸이 그림 전체 가운데에 한 번만 그리고 나머지 칸은 자리만 비운다."""
    spec = spec or {}
    if not items: return 0
    if spec.get('legend_span'): box = (spec['legend_span'][0], box[1], spec['legend_span'][1], box[3])
    widths = [42 + _text_width(name, size) for _, _, name in items]
    rows, row, used = [], [], 0          # 칸보다 길면 여러 줄로
    for item, w in zip(items, widths):
        if row and used + 26 + w > box[2] - box[0] - 30: rows.append(row); row, used = [], 0
        used += (26 if row else 0) + w; row.append((item, w))
    rows.append(row)
    if spec.get('legend') == 'space': return 14 + 38 * len(rows)
    for r, row in enumerate(rows):
        total = sum(w for _, w in row) + 26 * (len(row) - 1)
        x = (box[0] + box[2]) / 2 - total / 2; y = box[1] + 26 + 38 * r
        for (shape, style, name), w in row:
            if shape == 'fill': parts.append(_rect(x, y - 10, x + 30, y + 10, style, 1.6))
            else:
                dash, mark = style
                parts.append(_p(f'M{x:.1f},{y:.1f}L{x + 32:.1f},{y:.1f}', width=2.4, dash='8 5' if dash else ''))
                parts.append(_marker(mark, x + 16, y, 6))
            labels.append(_text(name, x + 40, y, size, 'left'))
            x += w + 26
    return 14 + 38 * len(rows)


def _series(spec):
    return [s for s in spec.get('series', []) if isinstance(s, dict)]


# ---------------------------------------------------------------- 검사
def check(spec):
    kind = spec.get('chart')
    if kind not in KINDS: return ['그래프는 chart: bar(막대), line(꺾은선), pie(원), band(띠), scatter(산점) 중 하나를 씁니다.']
    out = []
    if kind == 'pie':
        sl = spec.get('slices')
        if not isinstance(sl, list) or len(sl) < 2: return ['원그래프는 slices: [{"name":"농업","value":30},…] 2개 이상이 필요합니다.']
        if any(not _num(s.get('value')) or s['value'] < 0 for s in sl): out.append('원그래프의 value는 0 이상의 수입니다.')
        if len(sl) > 8: out.append('원그래프 조각은 8개까지 그립니다.')
        return out
    if kind == 'scatter':
        pts, lines = spec.get('points') or [], spec.get('lines') or []
        if not isinstance(pts, list) or not isinstance(lines, list) or not (pts or lines):
            return ['산점 그래프는 points: [{"label":"A","x":1,"y":2},…] 또는 lines: [{"name":"A","points":[[0,0],[1,2]]}]가 필요합니다.']
        if any(not isinstance(p, dict) or not (_num(p.get('x')) and _num(p.get('y'))) for p in pts): out.append('산점의 x, y는 수입니다.')
        for ln in lines:
            q = ln.get('points') if isinstance(ln, dict) else None
            if not isinstance(q, list) or len(q) < 2 or not all(isinstance(v, list) and len(v) == 2 and all(_num(c) for c in v) for v in q):
                out.append('lines의 points는 [x,y] 수 2개 이상입니다.')
        return out
    for name in ('y', 'x'):
        brk = (spec.get(name) or {}).get('break')
        if brk is not None and not (isinstance(brk, list) and len(brk) == 2 and all(_num(v) for v in brk) and brk[0] < brk[1]):
            out.append(f'{name}.break는 [자를 구간의 아래값, 위값]입니다(예: [-60, -10]).')
    cats = spec.get('categories')
    if not _need(spec, 'categories'): return [f'{"띠" if kind == "band" else "막대·꺾은선"}그래프는 categories(항목·연도 목록)가 필요합니다.']
    series = _series(spec)
    if not series: return ['series: [{"name":"A국","values":[…]}]가 필요합니다.']
    # 막대는 12개까지(막대가 너무 가늘어진다). 시간에 따른 꺾은선은 24개까지(2026-11-13: 항체 농도 그래프가 막혔다)
    most = 24 if kind == 'line' and all(s.get('as', 'line') == 'line' for s in series) else 12
    if len(cats) > most: out.append(f'항목은 {most}개까지 그립니다.')
    if len(series) > (8 if kind == 'band' else 5): out.append(f'계열은 {8 if kind == "band" else 5}개까지 그립니다.')
    for s in series:
        vals = s.get('values')
        if not isinstance(vals, list) or len(vals) != len(cats):
            out.append(f'계열 "{s.get("name", "")}"의 values 개수가 categories({len(cats)}개)와 같아야 합니다.'); continue
        if any(v is not None and not _num(v) for v in vals): out.append(f'계열 "{s.get("name", "")}"의 values는 수(빈 값은 null)입니다.')
        if s.get('axis') == 'right' and not isinstance(spec.get('y2'), dict): out.append('오른쪽 축(axis:"right") 계열에는 y2 눈금이 필요합니다.')
    if kind == 'band' and not out:
        for i, cat in enumerate(cats):
            total = sum(s['values'][i] or 0 for s in series)
            if abs(total - spec.get('total', 100)) > 0.6: out.append(f'띠그래프 "{cat}" 줄의 합이 {_fmt(total)}입니다. 구성비 합은 {_fmt(spec.get("total", 100))}이어야 합니다.')
    return out


# ---------------------------------------------------------------- 막대·꺾은선
def _bars_lines(spec, parts, labels, box):
    size = _size(box)
    cats, series = spec['categories'], _series(spec)
    bar = [s for s in series if (spec['chart'] == 'bar' and s.get('as') != 'line')]
    line = [s for s in series if s not in bar]
    left_vals = [v for s in series if s.get('axis') != 'right' for v in s['values'] if v is not None]
    if spec.get('stacked') and bar:
        left_vals += [sum(max(0, s['values'][i] or 0) for s in bar) for i in range(len(cats))]
    lo, hi, ticks = _scale(left_vals, spec.get('y'))
    right = [s for s in series if s.get('axis') == 'right']
    if right: lo2, hi2, ticks2 = _scale([v for s in right for v in s['values'] if v is not None], spec.get('y2'))
    items = []
    for i, s in enumerate(bar): items.append(('fill', BAR_FILLS[i % len(BAR_FILLS)], s.get('name', '')))
    for i, s in enumerate(line): items.append(('line', (i >= 2, MARKERS[i % len(MARKERS)]), s.get('name', '')))
    items = [it for it in items if it[2]] if len(series) > 1 or spec.get('legend') else []
    top = _legend(items, box, parts, labels, size, spec)
    shown = _ticks(spec.get('y'), ticks)
    tick_w = max([_text_width(text, size) for _, text in shown] or [10])
    xlab = (spec.get('x') or {}).get('label', '')
    L = box[0] + 40 + tick_w; R = box[2] - (50 + max(_text_width(_fmt(t), size) for t in ticks2) if right else 40)
    if xlab and not right: R -= _text_width(xlab, size) + 6      # 가로축 단위는 축 끝 오른쪽에(평가원 꼴)
    T = box[1] + top + 52; B = box[3] - 58
    Y, gap = _ymap(lo, hi, T, B, spec.get('y'))
    Y2 = (lambda v: B - (v - lo2) / (hi2 - lo2) * (B - T)) if right else Y
    if gap: shown = [(t, x) for t, x in shown if not (spec['y']['break'][0] < t < spec['y']['break'][1])]
    zero = Y(max(lo, min(hi, 0)))
    for t, text in shown:
        parts.append(_line((L - 8, Y(t)), (L, Y(t)), 1.6)); labels.append(_text(text, L - 14, Y(t), size, 'right'))
        if spec.get('grid') and t != lo: parts.append(_line((L, Y(t)), (R, Y(t)), 1, '3 5'))
    parts.append(_line((L, T - 14), (L, B), 2))
    parts.append(_line((L, B), (R, B), 2))
    if lo < 0 < hi: parts.append(_line((L, zero), (R, zero), 1.6))
    if right:
        parts.append(_line((R, T - 14), (R, B), 2))
        for t, text in _ticks(spec.get('y2'), ticks2):
            parts.append(_line((R, Y2(t)), (R + 8, Y2(t)), 1.6)); labels.append(_text(text, R + 14, Y2(t), size, 'left'))
        if (spec.get('y2') or {}).get('label'): labels.append(_text(spec['y2']['label'], box[2] - 8, T - 36, size, 'right'))
    if (spec.get('y') or {}).get('label'):         # 오른쪽 축이 있으면 두 축 이름이 겹치지 않게 칸의 양 끝에 붙인다
        labels.append(_text(spec['y']['label'], box[0] + 8, T - 36, size, 'left') if right else _text(spec['y']['label'], L - 8, T - 36, size, 'center'))
    slot = (R - L) / len(cats)
    names = [(i, str(c)) for i, c in enumerate(cats) if str(c).strip()]
    sequential = len(names) == len(cats) and all(re.match(r'\s*[\d(]', c) for _, c in names)      # 연도·월처럼 차례가 있는 수
    every, cat_size = 1, size
    if sequential:
        every = max(1, math.ceil((max(_text_width(c, size) for _, c in names) + 10) / slot))     # 좁으면 1, 4, 7, 10월처럼 건너뛴다
        if every > 1: every = max(every, 3)
    else:                     # 글로 된 항목은 건너뛰지 않고 글씨를 줄여 이웃과 겹치지 않게
        for (i, a), (j, b) in zip(names, names[1:]):
            room = (j - i) * slot - 12
            cat_size = min(cat_size, room / ((_text_width(a, 1) + _text_width(b, 1)) / 2))
        cat_size = max(15, int(cat_size))
    for i, cat in names:
        if i % every == 0: labels.append(_text(cat, L + slot * (i + .5), B + 26, cat_size))
    if xlab: labels.append(_text(xlab, R + 10, B + 26, size, 'left') if not right else _text(xlab, R, B + 26 + size + 4, size, 'right'))
    show = spec.get('values')
    if bar:
        group = slot * (.5 if spec.get('stacked') else min(.72, .26 * len(bar) + .2))
        bw = group if spec.get('stacked') else group / len(bar)
        for i in range(len(cats)):
            x = L + slot * (i + .5) - group / 2; base = 0
            for k, s in enumerate(bar):
                v = s['values'][i]
                if v is None: continue
                fill = BAR_FILLS[k % len(BAR_FILLS)]
                if spec.get('stacked'):
                    parts.append(_rect(x, Y(base), x + bw, Y(base + v), fill))
                    if show and abs(Y(base) - Y(base + v)) > size + 4 and fill != LINE:
                        labels.append(_text(_fmt(v), x + bw / 2, (Y(base) + Y(base + v)) / 2, SMALL))
                    base += v
                else:
                    yv = (Y2 if s.get('axis') == 'right' else Y)(v)
                    parts.append(_rect(x + k * bw, zero, x + (k + 1) * bw, yv, fill))
                    if show: labels.append(_text(_fmt(v), x + (k + .5) * bw, yv - 16 if v >= 0 else yv + 16, SMALL))
            if spec.get('stacked') and show == 'total':
                labels.append(_text(_fmt(base), x + bw / 2, Y(base) - 16, SMALL))
    for k, s in enumerate(line):
        Ys = Y2 if s.get('axis') == 'right' else Y
        pts = [(L + slot * (i + .5), Ys(v)) for i, v in enumerate(s['values']) if v is not None]
        runs, cur = [], []
        for i, v in enumerate(s['values']):
            if v is None: runs.append(cur); cur = []
            else: cur.append((L + slot * (i + .5), v))
        runs.append(cur)
        brk = spec['y']['break'] if gap and s.get('axis') != 'right' else None
        runs = [[(x, Ys(v)) for x, v in _split_at(run, brk)] for run in runs]
        for run in runs:
            if len(run) > 1: parts.append(_p('M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in run), width=2.4, dash='8 5' if k >= 2 else ''))
        for (x, y), v in zip(pts, [v for v in s['values'] if v is not None]):
            parts.append(_marker(MARKERS[k % len(MARKERS)], x, y, 7 if slot > 40 else 5))
            if show: labels.append(_text(_fmt(v), x, y - 22, SMALL))
        if s.get('name') and not items and len(series) > 1: labels.append(_text(s['name'], pts[-1][0] + 14, pts[-1][1], size, 'left'))
    if gap: _cut_band(parts, gap, L - 14, R + 6)
    return B + 26 + size


# ---------------------------------------------------------------- 띠
def _band(spec, parts, labels, box):
    size = _size(box)
    cats, series = spec['categories'], _series(spec)
    items = [('fill', BAND_FILLS[i % len(BAND_FILLS)], s.get('name', '')) for i, s in enumerate(series)]
    top = _legend(items, box, parts, labels, size, spec)
    total = spec.get('total', 100)
    L = box[0] + 40 + max(_text_width(c, size) for c in cats); R = box[2] - 40
    T = box[1] + top + 30; B = box[3] - 70
    row = (B - T) / len(cats); h = min(64, row * .58)
    X = lambda v: L + v / total * (R - L)
    for i, cat in enumerate(cats):
        cy = T + row * (i + .5); x = 0
        labels.append(_text(cat, L - 16, cy, size, 'right'))
        for k, s in enumerate(series):
            v = s['values'][i] or 0
            if v <= 0: continue
            parts.append(_rect(X(x), cy - h / 2, X(x + v), cy + h / 2, BAND_FILLS[k % len(BAND_FILLS)], 1.8))
            text = _fmt(v)
            if spec.get('values', True) and X(x + v) - X(x) > _text_width(text, SMALL) + 10:
                mid = (X(x) + X(x + v)) / 2
                if BAND_FILLS[k % len(BAND_FILLS)].startswith('hatch') or BAND_FILLS[k % len(BAND_FILLS)] == 'cross':       # 빗금 위 글씨가 읽히도록 흰 바탕
                    half = _text_width(text, SMALL) / 2 + 5
                    parts.append(f'<rect x="{mid - half:.1f}" y="{cy - size / 2:.1f}" width="{2 * half:.1f}" height="{size:.1f}" fill="white" stroke="none"/>')
                labels.append(_text(text, mid, cy, SMALL))
            x += v
    if spec.get('axis', True):
        for t in range(0, 101, 20):
            v = total * t / 100
            parts.append(_line((X(v), B), (X(v), B + 8), 1.6)); labels.append(_text(_fmt(v), X(v), B + 26, size))
        parts.append(_line((L, B), (R, B), 1.8))
        labels.append(_text((spec.get('x') or {}).get('label', '(%)'), R, B + 26 + size + 4, size, 'right'))
    return B + 50


# ---------------------------------------------------------------- 원
def _pie(spec, parts, labels, box):
    size = _size(box)
    sl = spec['slices']; total = sum(s['value'] for s in sl) or 1
    unit = spec.get('unit', '%')
    cap = 40 if spec.get('title') else 0
    r = min(box[2] - box[0], box[3] - box[1] - cap) * .36
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3] - cap) / 2 + 6
    a = -math.pi / 2
    for k, s in enumerate(sl):
        frac = s['value'] / total; b = a + frac * 2 * math.pi
        fill = PIE_FILLS[k % len(PIE_FILLS)]
        if frac >= .9999: parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" stroke="{LINE}" stroke-width="2.2"/>')
        elif frac > 0:
            p, q = (cx + r * math.cos(a), cy + r * math.sin(a)), (cx + r * math.cos(b), cy + r * math.sin(b))
            parts.append(_p(f'M{cx:.1f},{cy:.1f}L{p[0]:.1f},{p[1]:.1f}A{r:.1f},{r:.1f} 0 {1 if frac > .5 else 0} 1 {q[0]:.1f},{q[1]:.1f}Z', fill=fill, width=2.2))
        mid = (a + b) / 2; name, value = s.get('name', ''), _fmt(s['value']) + unit
        if frac >= .08:
            lx, ly = cx + r * .62 * math.cos(mid), cy + r * .62 * math.sin(mid)
            if name: labels.append(_text(name, lx, ly - size * .62, size)); labels.append(_text(value, lx, ly + size * .62, size))
            else: labels.append(_text(value, lx, ly, size))
        elif frac > 0:
            p = (cx + r * math.cos(mid), cy + r * math.sin(mid)); q = (cx + r * 1.16 * math.cos(mid), cy + r * 1.16 * math.sin(mid))
            parts.append(_line(p, q, 1.4))
            side = 'left' if math.cos(mid) >= 0 else 'right'
            labels.append(_text(f'{name} {value}'.strip(), q[0] + (6 if side == 'left' else -6), q[1], SMALL, side))
        a = b
    if spec.get('title'): labels.append(_text(spec['title'], cx, cy + r + 34, size))
    return cy + r + (50 if spec.get('title') else 4)


# ---------------------------------------------------------------- 산점
def _scatter(spec, parts, labels, box):
    """점(대상의 위치)과 연속한 가로축의 측정값 꺾은선(lines: 전압-전류, 시간-농도처럼 가로축 간격이 수인 자료)."""
    size = _size(box)
    pts = spec.get('points') or []; ax, ay = spec.get('x') or {}, spec.get('y') or {}
    lines = [ln for ln in spec.get('lines') or [] if isinstance(ln, dict)]
    xs = [p['x'] for p in pts] + [q[0] for ln in lines for q in ln['points']]
    ys = [p['y'] for p in pts] + [q[1] for ln in lines for q in ln['points']]
    lo_x, hi_x, tx = _scale(xs, ax)
    lo_y, hi_y, ty = _scale(ys, ay)
    sx, sy = _ticks(ax, tx), _ticks(ay, ty)
    show_x, show_y = bool(sx), bool(sy)
    items = [('line', (k >= 2, MARKERS[k % len(MARKERS)]), ln.get('name', '')) for k, ln in enumerate(lines)]
    items = [it for it in items if it[2]] if len(lines) > 1 else []
    top = _legend(items, box, parts, labels, size, spec)
    L = box[0] + 40 + (max(_text_width(text, size) for _, text in sy) if show_y else 10)
    R, T, B = box[2] - 60, box[1] + 60 + top, box[3] - 62 - (size + 6 if show_x and ax.get('label') else 0)
    X = lambda v: L + (v - lo_x) / (hi_x - lo_x) * (R - L)
    Y, gap = _ymap(lo_y, hi_y, T, B, ay)
    if gap: sy = [(t, x) for t, x in sy if not (ay['break'][0] < t < ay['break'][1])]
    parts.append(_line((L, B), (R + 20, B), 2)); parts.append(_line((L, B), (L, T - 20), 2))
    for t, text in sy: parts.append(_line((L - 8, Y(t)), (L, Y(t)), 1.6)); labels.append(_text(text, L - 14, Y(t), size, 'right'))
    for t, text in sx: parts.append(_line((X(t), B), (X(t), B + 8), 1.6)); labels.append(_text(text, X(t), B + 26, size))
    if ay.get('label'): labels.append(_text(ay['label'], L, T - 44, size))
    if ax.get('label'): labels.append(_text(ax['label'], R + 20, B + 26 + (size + 6 if show_x else 0), size, 'right'))
    for p in pts:
        x, y = X(p['x']), Y(p['y'])
        if spec.get('guides') or p.get('guides'):
            parts.append(_line((x, y), (x, B), 1.2, '5 4')); parts.append(_line((x, y), (L, y), 1.2, '5 4'))
        parts.append(_marker(p.get('marker', 'dot'), x, y))
        if p.get('label'): labels.append(_text(p['label'], x + 14, y - 20, size, 'left'))
    for k, ln in enumerate(lines):
        brk = ay.get('break') if gap else None
        run = [(x, Y(v)) for x, v in _split_at(sorted((X(a), b) for a, b in ln['points']), brk)]
        parts.append(_p('M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in run), width=2.4, dash='8 5' if k >= 2 else ''))
        if ln.get('markers', True):
            for a, b in ln['points']: parts.append(_marker(MARKERS[k % len(MARKERS)], X(a), Y(b)))
        if ln.get('name') and len(lines) == 1 and ln.get('tag'):
            labels.append(_text(ln['name'], run[-1][0] + 14, run[-1][1] - 18, size, 'left'))
        if spec.get('values'):
            for a, b in ln['points']: labels.append(_text(_fmt(b), X(a), Y(b) - 22, SMALL))
    if gap: _cut_band(parts, gap, L - 14, R + 22)
    return B + 40


DRAW = {'bar': _bars_lines, 'line': _bars_lines, 'band': _band, 'pie': _pie, 'scatter': _scatter}


# 단위는 기호로 쓴다(lux, V, A …). 괄호 안에 한글 단위 이름이 오면 기호로 바꾼다.
UNIT_NAMES = {'럭스': 'lux', 'lx': 'lux', '볼트': 'V', '암페어': 'A', '옴': 'Ω', '와트': 'W', '줄': 'J', '뉴턴': 'N', '킬로그램': 'kg', '그램': 'g',
              '미터': 'm', '센티미터': 'cm', '밀리미터': 'mm', '킬로미터': 'km', '초': 's', '헤르츠': 'Hz', '파스칼': 'Pa', '리터': 'L', '밀리리터': 'mL'}
UNITS = {'㎢': 'km²', '㎡': 'm²', '㎞': 'km', '㎜': 'mm', '㎝': 'cm', '㎏': 'kg', '℃': '°C', '㎖': 'mL', 'ℓ': 'L'}
MATH_ONLY = {'‰': '‰', 'Ω': '\\Omega'}       # 한글 글꼴(신명 중명조)에 없는 기호. 수식 글씨로 따로 놓는다.


def _fonts_safe(label):
    """한글 글꼴(신명 중명조)로 못 쓰는 글씨를 고친다: 단위 기호(㎢→km², 럭스→lux), 글꼴에 없는 ‰·Ω와
    $X$·$t_{1}$ 같은 변수는 수식 글씨 조각으로 나눠 한 줄에 잇는다(변수만 수식 글꼴, 나머지는 명조)."""
    text = str(label['text'])
    for a, b in UNITS.items(): text = text.replace(a, b)
    text = re.sub(r'\(([가-힣A-Za-z]+)\)', lambda m: '(' + UNIT_NAMES.get(m.group(1), m.group(1)) + ')', text)
    if text.count('$') % 2: text = text.replace('$', '')
    outside = re.split(r'(\$[^$]+\$)', text)
    text = ''.join(t if t.startswith('$') else ''.join('$' + MATH_ONLY[ch] + '$' if ch in MATH_ONLY else ch for ch in t) for t in outside)
    if '$' not in text: return [{**label, 'text': text}]
    from .diagrams_physics import _measure
    size, pieces = label['size'], []
    for t in re.split(r'(\$[^$]+\$)', text):
        if not t: continue
        if t.startswith('$'): pieces.append(('physics', t, _measure(t, size)[0]))
        elif t.strip(): pieces.append(('korean', t.strip(), _text_width(t.strip(), size) + (size * .25 if t != t.strip() else 0)))
    total = sum(w for _, _, w in pieces)
    plain = re.sub(r'\$|\\[A-Za-z]+|[{}_^]', '', str(label['text']))
    x = max(8, min(W - total - 8, label['x'] + _text_width(plain, size) / 2 - total / 2))
    out = []
    for kind, t, w in pieces:
        out.append({**label, 'kind': kind, 'text': t, 'x': round(x, 1)}); x += w
    return out


def render(spec, parts, labels, box=FRAME):
    start = len(labels)
    if spec.get('title') and spec['chart'] != 'pie':       # 그래프 제목은 위 가운데(원그래프는 아래)
        title = spec['title'].strip()
        title = title.strip('〈〉<>')
        title = '<' + title + '>'       # 평가원 꼴 〈 〉. 신명 중명조에 〈 〉 글자가 없어 < >로 쓴다
        labels.append(_text(title, (box[0] + box[2]) / 2, box[1] + 24, MAIN))
        box = (box[0], box[1] + 44, box[2], box[3])
    bottom = DRAW[spec['chart']](spec, parts, labels, box)
    labels[start:] = [x for lab in labels[start:] if str(lab['text']).strip() for x in _fonts_safe(lab)]      # 빈 항목 이름은 글씨를 만들지 않는다
    return bottom


PROMPT = """
그래프 자료(사회·과학 공통, 앱이 그림): 수치 자료는 자료가 보여 줄 것에 맞는 꼴로 낸다. 모든 표를 그래프로 바꾸지 않는다.
- 그래프가 맞는 경우: 시간에 따른 변화·추세는 꺾은선(line), 지역·집단·항목 사이 크기 비교는 막대(bar), 한 전체의 구성비는 원(pie), 여러 시점·집단의 구성비 비교는 띠(band), 두 지표로 본 대상의 위치·관계는 산점(scatter). 학생이 그래프의 모양(증가·감소, 크고 작음, 비중)을 읽어 판단하게 할 때 쓴다.
- 표가 맞는 경우: 정확한 값을 읽어 계산해야 할 때, 단위가 다른 여러 지표를 대상마다 대조할 때, ○·× 여부나 글로 된 특징이 섞일 때, 값이 몇 개뿐이어서 그래프가 오히려 번거로울 때. 이때는 지금처럼 table 블록을 쓴다.
- 합이 100%인 구성비는 띠(여러 대상)나 원(한 대상)으로 그린다. 구성비 항목을 막대로 늘어놓지 않는다. 항목 이름(categories)과 계열 이름은 짧게 쓰고, 긴 설명은 문두로 뺀다(예: 주사 시점은 "$t_{1}$", "$t_{2}$"로 쓰고 문두에서 밝힌다. 나머지 칸은 빈 문자열).
- 평가원 사회·과학탐구처럼 한 문항에 그래프와 표를 함께 둘 수 있다. 같은 수치를 그래프와 표로 두 번 싣지 않는다.
그래프로 낼 때는 image 블록 하나를 strict로 두고 image_locked 첫 글자부터 `도식: ` 뒤에 JSON 하나만 쓴다(image_creative·글씨 프롬프트는 빈 문자열). 글씨는 평문이다(LaTeX 금지). 앱이 흑백 평가원 꼴(회색 단계·빗금·표지 모양)로 그리고 범례·눈금을 만든다.
- 막대: {"type":"chart","chart":"bar","categories":["2000년","2010년","2020년"],"series":[{"name":"A국","values":[12,18,25]},{"name":"B국","values":[20,17,15]}],"y":{"label":"(%)","min":0,"max":30,"step":10},"values":false} stacked:true는 쌓은 막대. 계열에 "as":"line"을 주면 막대 위에 꺾은선을 함께 그리고, "axis":"right"와 "y2":{"label":"(명)",…}로 오른쪽 축을 쓴다.
- 꺾은선: {"type":"chart","chart":"line","categories":[…],"series":[{"name":"출생률","values":[…]},…],"y":{"label":"(‰)"},"x":{"label":"(년)"}} 빈 값은 null.
- 원: {"type":"chart","chart":"pie","slices":[{"name":"1차 산업","value":10},{"name":"2차 산업","value":30},{"name":"3차 산업","value":60}],"unit":"%","title":"(가) 지역"} 12시 방향부터 시계 방향으로 그린다.
- 띠: {"type":"chart","chart":"band","categories":["1990년","2020년"],"series":[{"name":"유소년층","values":[25,12]},{"name":"청장년층","values":[70,72]},{"name":"노년층","values":[5,16]}]} 줄마다 합이 100이어야 한다.
- 산점: {"type":"chart","chart":"scatter","points":[{"label":"A","x":2,"y":80},…],"x":{"label":"1인당 GDP(만 달러)"},"y":{"label":"도시화율(%)","ticks":false}} ticks:false면 눈금 수를 감추고 상대 위치만 보인다(x·y 모두, 막대·꺾은선의 y도 같다). ticks:[1000,4000,8000]이면 그 값에만 눈금을 둔다. guides:true는 점에서 두 축으로 점선. 가로축도 수인 측정값(전압-전류, 시간-농도, 빛의 세기-기포 수)은 "lines":[{"name":"A","points":[[0,0],[1,2],[2,4]]}]로 점을 이은 꺾은선을 그린다(계열이 둘 이상이면 범례를 만든다).
- 축 자르기: 세로축 범위가 커서 아래쪽 눈금끼리 붙으면(예: 막전위 -80, -75, -70과 +30) "y":{"min":-80,"max":40,"break":[-50,-10],"ticks":[-80,-75,-70,0,30]}처럼 break로 그래프 전체를 물결로 잘라 접는다(평가원 꼴). 앱이 실제 비율로 그린 뒤 잘라 붙이므로 선의 기울기는 그대로다. 잘린 아래·위 조각이 각각 그래프 높이의 1/3 이상이 되게 자를 곳을 정하고, 자른 구간 안의 눈금은 쓰지 않는다.
- 글씨 규칙: 그래프 안 글씨는 앱이 본문 명조 한 가지, 두 크기로 맞춘다. 단위는 축 이름 뒤 괄호에 기호로 쓴다(예: \"빛의 세기(lux)\", \"전압(V)\", \"(mm)\", \"(°C)\", \"(명/km²)\"). 럭스·볼트 같은 한글 단위 이름은 쓰지 않는다. 빛의 세기는 lx가 아니라 lux로 쓴다(교사 지정). 문두·자료의 수치에도 같은 단위 기호를 쓴다.
- 그래프마다 이름이 필요하면 "title":"도시화율 변화"를 쓴다(앱이 <도시화율 변화>로 그림 위 가운데에 쓴다). 계열 이름·항목 이름의 기호는 $X$처럼 써도 된다.
- y의 min·max·step을 생략하면 앱이 0부터 보기 좋은 눈금을 정한다. values:true면 막대·점 위에 값을 쓴다(값을 읽어 계산해야 하는 문항이면 values:true로 둔다). 값이 그대로 답이 되면 values를 끄고 눈금으로 읽게 한다.
- (가)(나) 두 그래프는 {"type":"panels","layout":"row","items":[{"type":"chart",…,"caption":"(가)"},{"type":"chart",…,"caption":"(나)"}]}로 나란히 놓는다.
- 그래프의 수가 문두·〈보기〉·정답과 맞는지 review_note에 적는다.
"""
