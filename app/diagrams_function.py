"""수학 함수 그래프: 식으로 주는 곡선, 구간과 끝점(열린 점·닫힌 점), 점근선, 원, 선분, 넓이. 평가원 수학 그림 꼴.

AI가 곡선을 손으로 그리지 않고 식과 구간만 쓰면 앱이 계산해서 그린다(곡선이 식과 어긋나지 않는다).
식은 x 하나의 파이썬 식이고 허용한 함수만 계산한다(eval을 쓰지 않는다).
"""
import ast
import math

from .diagrams import LINE, W, H, _p, _line, _arrow, _need
from .diagrams_physics import _lab, _lab_side, _measure, _width, TEXT

FRAME = (0, 0, W, H)
SHADE = '#d9d9d9'
FUNCS = {'sqrt': math.sqrt, 'exp': math.exp, 'ln': math.log, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
         'abs': abs, 'Abs': abs, 'floor': math.floor, 'ceil': math.ceil, 'cbrt': lambda v: math.copysign(abs(v) ** (1 / 3), v),
         'asin': math.asin, 'acos': math.acos, 'atan': math.atan}
CONSTS = {'pi': math.pi, 'e': math.e}
def _pow(a, b):
    """음수의 홀수 제곱근(x**(1/3))은 실수로 계산한다. 그 밖의 음수 분수 거듭제곱은 정의되지 않는다."""
    if a < 0 and b != int(b):
        k = round(1 / b) if b else 0
        if k and abs(1 / b - k) < 1e-9 and k % 2: return -((-a) ** b)
        raise ValueError('정의되지 않는 거듭제곱')
    return a ** b


OPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
       ast.Pow: _pow, ast.Mod: lambda a, b: a % b}


def compile_expr(source):
    """'x**2 - 2*x', 'log(x, 2)', 'floor(x)', 'abs(x-1)', '2^x' 같은 식을 계산 함수로. 허용하지 않은 것은 ValueError."""
    text = str(source).replace('^', '**').replace('−', '-').strip()
    if not text or len(text) > 200: raise ValueError('식이 비었거나 너무 깁니다.')
    try: tree = ast.parse(text, mode='eval')
    except SyntaxError: raise ValueError(f'식을 읽을 수 없습니다: {source}') from None
    if sum(1 for _ in ast.walk(tree)) > 120: raise ValueError('식이 너무 복잡합니다.')

    def build(n):
        if isinstance(n, ast.Constant) and type(n.value) in (int, float): v = float(n.value); return lambda x: v
        if isinstance(n, ast.Name):
            if n.id == 'x': return lambda x: x
            if n.id in CONSTS: v = CONSTS[n.id]; return lambda x: v
            raise ValueError(f'식에는 x만 변수로 씁니다: {n.id}')
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            f = build(n.operand); return (lambda x: -f(x)) if isinstance(n.op, ast.USub) else f
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            a, b, op = build(n.left), build(n.right), OPS[type(n.op)]; return lambda x: op(a(x), b(x))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and not n.keywords:
            args = [build(a) for a in n.args]
            if n.func.id == 'log':
                if len(args) == 1: return lambda x: math.log(args[0](x))
                if len(args) == 2: return lambda x: math.log(args[0](x)) / math.log(args[1](x))
            if n.func.id in FUNCS and len(args) == 1:
                f = FUNCS[n.func.id]; return lambda x: f(args[0](x))
            if n.func.id in ('min', 'max') and len(args) >= 2:
                f = min if n.func.id == 'min' else max; return lambda x: f(g(x) for g in args)
        raise ValueError(f'허용하지 않는 식입니다: {ast.unparse(n)} (쓸 수 있는 함수: sqrt, exp, log, ln, sin, cos, tan, abs, floor, ceil, min, max)')
    return build(tree.body)


def _value(f, x):
    try:
        y = f(x)
        return y if isinstance(y, (int, float)) and math.isfinite(y) else None
    except (ValueError, ZeroDivisionError, OverflowError, TypeError):
        return None


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _pt(v):
    return isinstance(v, (list, tuple)) and len(v) == 2 and all(_num(c) for c in v)


# ---------------------------------------------------------------- 검사
def check(spec):
    out = []
    view = spec.get('view')
    if not (isinstance(view, list) and len(view) == 4 and all(_num(v) for v in view) and view[0] < view[1] and view[2] < view[3]):
        return ['함수 그래프는 view: [x최소, x최대, y최소, y최대]가 필요합니다.']
    if not (spec.get('curves') or spec.get('circles') or spec.get('segments') or spec.get('points')):
        out.append('curves(식으로 주는 곡선), circles, segments, points 중 하나는 있어야 합니다.')
    for c in spec.get('curves') or []:
        try: f = compile_expr(c.get('expr', ''))
        except ValueError as e: out.append(str(e)); continue
        dom = c.get('domain', view[:2])
        if not (isinstance(dom, list) and len(dom) == 2 and all(_num(v) for v in dom) and dom[0] < dom[1]):
            out.append(f'곡선 {c.get("expr")}의 domain은 [시작, 끝]입니다.'); continue
        xs = [dom[0] + (dom[1] - dom[0]) * k / 50 for k in range(51)]
        if sum(_value(f, x) is not None for x in xs) < 3: out.append(f'곡선 {c.get("expr")}을(를) domain {dom}에서 계산할 수 없습니다.')
        for end in c.get('ends') or []:
            if end not in ('open', 'closed', 'none', '', None): out.append('ends는 ["closed","open"]처럼 closed·open·none으로 씁니다.')
    for s in spec.get('segments') or []:
        if not (_pt(s.get('from')) and _pt(s.get('to'))): out.append('선분은 {"from":[x,y],"to":[x,y]}로 씁니다.')
    for c in spec.get('circles') or []:
        if not (_pt(c.get('center')) and _num(c.get('r')) and c['r'] > 0): out.append('원은 {"center":[a,b],"r":양수}로 씁니다.')
    for p in spec.get('points') or []:
        if not _pt(p.get('at')): out.append('점은 {"at":[x,y],"label":"$P$"}로 씁니다.')
    for f in spec.get('fills') or []:
        if not (_num(f.get('from')) and _num(f.get('to'))): out.append('넓이 칠하기는 {"curve":0,"from":a,"to":b}로 씁니다.')
    return out


# ---------------------------------------------------------------- 그리기
class Frame:
    def __init__(self, view, box, equal):
        self.x0, self.x1, self.y0, self.y1 = view
        L, T, R, B = box[0] + 70, box[1] + 50, box[2] - 70, box[3] - 60
        sx, sy = (R - L) / (self.x1 - self.x0), (B - T) / (self.y1 - self.y0)
        if equal:
            s = min(sx, sy); cx, cy = (L + R) / 2, (T + B) / 2
            L, R = cx - s * (self.x1 - self.x0) / 2, cx + s * (self.x1 - self.x0) / 2
            T, B = cy - s * (self.y1 - self.y0) / 2, cy + s * (self.y1 - self.y0) / 2
            sx = sy = s
        self.L, self.T, self.R, self.B, self.sx, self.sy = L, T, R, B, sx, sy

    def __call__(self, x, y):
        return self.L + (x - self.x0) * self.sx, self.B - (y - self.y0) * self.sy


def _runs(f, a, b, fr, n=700):
    """[a,b]에서 곡선을 촘촘히 계산해 화면 안 조각들로. 끊어진 곳(점근선·계단)과 화면 밖은 선을 잇지 않는다."""
    ylo, yhi = fr.y0 - (fr.y1 - fr.y0) * .02, fr.y1 + (fr.y1 - fr.y0) * .02
    span = fr.y1 - fr.y0
    eps = (b - a) * 1e-7          # 구간 끝 값은 안쪽에서 다가간 값(계단 함수가 다음 계단으로 튀지 않게)
    xs = [a + eps + (b - a - 2 * eps) * k / n for k in range(n + 1)]
    ys = [_value(f, x) for x in xs]
    steps = sorted(abs(ys[i] - ys[i - 1]) for i in range(1, len(ys)) if ys[i] is not None and ys[i - 1] is not None)
    typical = steps[len(steps) // 2] if steps else 0
    runs, cur = [], []
    for i, (x, y) in enumerate(zip(xs, ys)):
        prev = ys[i - 1] if i else None
        dy = abs(y - prev) if prev is not None and y is not None else 0
        jump = dy > span * .35 or (dy > span * .03 and dy > 60 * typical)      # 점근선·계단에서 선을 잇지 않는다
        if y is None or jump:
            if len(cur) > 1: runs.append(cur)
            cur = []
            if y is None: continue
        inside = ylo <= y <= yhi
        if cur and not inside:          # 화면 밖으로 나가는 곳은 경계까지만
            py = cur[-1][1]; edge = yhi if y > yhi else ylo
            t = (edge - py) / (y - py) if y != py else 0
            cur.append((cur[-1][0] + (x - cur[-1][0]) * t, edge)); runs.append(cur); cur = []; continue
        if not cur and inside and prev is not None and not jump and not (ylo <= prev <= yhi):   # 화면 안으로 들어오는 곳
            edge = yhi if prev > yhi else ylo; t = (edge - prev) / (y - prev) if y != prev else 0
            cur.append((xs[i - 1] + (x - xs[i - 1]) * t, edge))
        if inside: cur.append((x, y))
    if len(cur) > 1: runs.append(cur)
    return runs


def _dot(c, kind):
    if kind == 'open': return f'<circle cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="6.5" fill="white" stroke="{LINE}" stroke-width="2.2"/>'
    return f'<circle cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="6.5" fill="{LINE}" stroke="none"/>'


def _tex(v):
    if isinstance(v, str): return v
    return '$' + (str(int(v)) if float(v).is_integer() else f'{v:g}') + '$'


def _box(label):
    """글씨 객체가 차지하는 상자 (왼, 위, 오른, 아래)."""
    text, size = label['text'], label['size']
    wide, high = _measure(text, size) if '$' in text else (_width(text, size), size)
    return label['x'], label['y'], label['x'] + wide, label['y'] + high


def _segment_pts(a, b, step=6):
    n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / step))
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]


def _gap(box, pts):
    l, t, r, b = box
    return min((math.hypot(max(l - x, 0, x - r), max(t - y, 0, y - b)) for x, y in pts), default=1e9)


def _place(text, anchors, ink, labels, box, own=(), others=()):
    """곡선 이름을 선·다른 글씨와 겹치지 않는 자리에 둔다(2026-11-12: 곡선 끝 기본 자리에서 이름이 선을 덮었다).
    anchors는 곡선 끝에서부터 고른 기준점, ink는 그림의 선 위 점들이다. 가장 덜 겹치는 자리를 고른다.
    이름은 자기 곡선에 다른 곡선보다 가까워야 한다(어느 곡선의 이름인지 헷갈리지 않게)."""
    size = round(26 * TEXT)
    wide, high = _measure(text, size)
    taken = [_box(l) for l in labels]
    best = None
    for rank, (px, py) in enumerate(anchors):
        for dx, dy in ((1, 0), (.75, -1), (0, -1), (-.75, -1), (-1, 0), (.75, 1), (0, 1), (-.75, 1)):
            cx, cy = px + dx * (wide / 2 + 12), py + dy * (high / 2 + 10)
            l, t, r, b = cx - wide / 2, cy - high / 2, cx + wide / 2, cy + high / 2
            out = l < box[0] + 8 or r > box[2] - 8 or t < box[1] + 8 or b > box[3] - 8
            touch = sum(1 for x, y in ink if l - 5 <= x <= r + 5 and t - 5 <= y <= b + 5)
            clash = sum(1 for L, T, R, B in taken if l < R + 6 and r > L - 6 and t < B + 6 and b > T - 6)
            near = _gap((l, t, r, b), own) if own else 0
            unclear = any(_gap((l, t, r, b), pts) < near + 4 for pts in others) if own else False
            score = (out * 1000 + clash * 500 + touch * 20 + unclear * 300) + rank * 3 + (abs(dx) + abs(dy)) * .5
            if best is None or score < best[0]: best = (score, cx, cy)
    return _lab(text, best[1], best[2], size, scaled=True)


def _mark(text, p, ways, ink, labels, box, gap=7):
    """눈금 숫자·원점 O: 정해진 쪽부터 차례로 시도해 선·글씨와 겹치지 않는 첫 자리에 둔다."""
    size = round(24 * TEXT)
    wide, high = _measure(text, size) if '$' in text else (_width(text, size), size)
    taken = [_box(l) for l in labels]
    best = None
    for rank, (dx, dy) in enumerate(ways):
        cx, cy = p[0] + dx * (wide / 2 + gap), p[1] + dy * (high / 2 + gap)
        l, t, r, b = cx - wide / 2, cy - high / 2, cx + wide / 2, cy + high / 2
        out = l < box[0] + 4 or r > box[2] - 4 or t < box[1] + 4 or b > box[3] - 4
        touch = sum(1 for x, y in ink if l - 3 <= x <= r + 3 and t - 3 <= y <= b + 3)
        clash = sum(1 for L, T, R, B in taken if l < R + 3 and r > L - 3 and t < B + 3 and b > T - 3)
        score = out * 1000 + clash * 500 + touch * 20 + rank * 6
        if best is None or score < best[0]: best = (score, cx, cy)
    return _lab(text, best[1], best[2], size, scaled=True)


def render(spec, parts, labels, box=FRAME):
    view = spec['view']
    fr = Frame(view, box, spec.get('equal', False))
    ox = min(max(0, fr.x0), fr.x1); oy = min(max(0, fr.y0), fr.y1)
    O = fr(ox, oy)
    later = []         # 끝점·점은 곡선 위에 그린다
    ink = []           # 그림의 선 위 점(곡선 이름 자리를 고를 때 피한다)
    named = []         # (이름, 곡선 끝에서부터의 기준점) — 선을 다 그린 뒤 자리를 고른다
    ends_drawn = []    # (화면 점, closed/open)
    curve_ink = []     # 곡선마다의 선 위 점
    curves = []
    for c in spec.get('curves') or []:
        f = compile_expr(c['expr'])
        a, b = c.get('domain', view[:2])
        a, b = max(a, fr.x0), min(b, fr.x1)
        curves.append((f, a, b))
    for fill in spec.get('fills') or []:      # 넓이: 곡선과 x축 사이 또는 두 곡선 사이
        f = curves[fill.get('curve', 0)][0]; g = curves[fill['with']][0] if _num(fill.get('with')) else (lambda x: 0)
        xs = [fill['from'] + (fill['to'] - fill['from']) * k / 200 for k in range(201)]
        top = [fr(x, _value(f, x) or 0) for x in xs]; bottom = [fr(x, _value(g, x) or 0) for x in reversed(xs)]
        parts.append(f'<path d="M{"L".join(f"{p[0]:.1f},{p[1]:.1f}" for p in top + bottom)}Z" fill="{SHADE}" stroke="none"/>')
    for a in spec.get('asymptotes') or []:
        if _num(a.get('x')): parts.append(_line(fr(a['x'], fr.y0), fr(a['x'], fr.y1), 1.5, '7 5')); ink += _segment_pts(fr(a['x'], fr.y0), fr(a['x'], fr.y1))
        if _num(a.get('y')): parts.append(_line(fr(fr.x0, a['y']), fr(fr.x1, a['y']), 1.5, '7 5')); ink += _segment_pts(fr(fr.x0, a['y']), fr(fr.x1, a['y']))
        if a.get('label'):
            at = fr(a['x'], fr.y1) if _num(a.get('x')) else fr(fr.x1, a['y'])
            labels.append(_lab_side(a['label'], at[0], at[1], 'right' if _num(a.get('x')) else 'up', 24, 8))
    for g in spec.get('guides') or []:      # 점에서 두 축으로 점선
        p = fr(*g); parts.append(_line(p, (p[0], O[1]), 1.4, '5 4')); parts.append(_line(p, (O[0], p[1]), 1.4, '5 4'))
        ink += _segment_pts(p, (p[0], O[1])) + _segment_pts(p, (O[0], p[1]))
    # 축(평가원 꼴: 화살표, 오른쪽 끝 x, 위쪽 끝 y, 원점 O)
    parts.append(_arrow((fr.L - 20, O[1]), (fr.R + 30, O[1]), 2, 13)); parts.append(_arrow((O[0], fr.B + 20), (O[0], fr.T - 30), 2, 13))
    ink += _segment_pts((fr.L - 20, O[1]), (fr.R + 30, O[1])) + _segment_pts((O[0], fr.B + 20), (O[0], fr.T - 30))
    labels.append(_lab_side(spec.get('x_label', '$x$'), fr.R + 34, O[1], 'right', 24, 4))
    labels.append(_lab_side(spec.get('y_label', '$y$'), O[0], fr.T - 30, 'up', 24, 4))
    # 눈금 숫자와 O는 선을 다 그린 뒤 곡선과 겹치지 않는 쪽에 둔다(2026-11-12: 곡선이 축을 지나는 곳에서 -3, 2가 곡선에 덮였다)
    marks = []
    if spec.get('origin', '$O$') and ox == 0 and oy == 0:
        marks.append((spec.get('origin', '$O$'), O, ((-1, 1), (1, 1), (-1, -1), (1, -1))))
    for t in spec.get('x_ticks') or []:
        v, text = (t if isinstance(t, list) else (t, _tex(t)))
        p = fr(v, oy); parts.append(_line((p[0], p[1] - 6), (p[0], p[1] + 6), 1.6))
        marks.append((_tex(text), p, ((0, 1), (-1, 1), (1, 1), (-1, -1), (1, -1), (0, -1))))
    for t in spec.get('y_ticks') or []:
        v, text = (t if isinstance(t, list) else (t, _tex(t)))
        p = fr(ox, v); parts.append(_line((p[0] - 6, p[1]), (p[0] + 6, p[1]), 1.6))
        marks.append((_tex(text), p, ((-1, 0), (-1, -1), (-1, 1), (1, -1), (1, 1), (1, 0))))
    for (f, a, b), c in zip(curves, spec.get('curves') or []):
        runs = _runs(f, a, b, fr)
        mine = []
        for run in runs:
            pts = [fr(x, y) for x, y in run]
            parts.append(_p('M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in pts), width=2.6, dash='9 6' if c.get('dash') else ''))
            mine += [q for i, q in enumerate(pts) if i % 3 == 0 or i == len(pts) - 1]
        ink += mine; curve_ink.append(mine)
        ends = c.get('ends') or []
        eps = (b - a) * 1e-7
        for end, x in zip(ends, (a + eps, b - eps)):      # 끝점의 높이는 구간 안쪽에서 다가간 값(계단 함수의 빈 점)
            y = _value(f, x)
            if end in ('open', 'closed') and y is not None and fr.y0 <= y <= fr.y1: ends_drawn.append((fr(x, y), end))
        if c.get('label'):
            if _num(c.get('label_at')) and _value(f, c['label_at']) is not None:
                p = fr(c['label_at'], min(max(_value(f, c['label_at']), fr.y0), fr.y1)); side = c.get('label_side', 'right')
                labels.append(_lab_side(c['label'], p[0], p[1], side, 26, 12))
            elif runs:     # 평가원 꼴: 곡선 이름은 곡선이 끝나는 곳 근처, 선과 겹치지 않는 자리에
                last = [fr(x, y) for x, y in runs[-1]]; first = [fr(x, y) for x, y in runs[0]]
                picks = [last[-1]] + [last[int((len(last) - 1) * k)] for k in (.93, .85, .75, .62, .5)]
                picks += [first[0]] + [first[int((len(first) - 1) * k)] for k in (.07, .15)]     # 다른 끝도 후보로
                named.append((_tex(c['label']), picks, len(curve_ink) - 1))
    # 두 조각이 이어지는 꺾인 점(양쪽 모두 closed)은 평가원 그래프처럼 점을 찍지 않는다
    for p, kind in ends_drawn:
        joined = kind == 'closed' and sum(1 for q, k in ends_drawn if k == 'closed' and math.dist(p, q) < 2) > 1
        if not joined: later.append(_dot(p, kind))
    for c in spec.get('circles') or []:
        (cx, cy), r = fr(*c['center']), c['r']
        parts.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{r * fr.sx:.1f}" ry="{r * fr.sy:.1f}" fill="none" stroke="{LINE}" stroke-width="2.6"/>')
        ink += [(cx + r * fr.sx * math.cos(k * math.pi / 40), cy + r * fr.sy * math.sin(k * math.pi / 40)) for k in range(80)]
        if c.get('label'):
            p = fr(c['center'][0] + r * .72, c['center'][1] + r * .72)
            labels.append(_lab_side(c['label'], p[0], p[1], 'right', 26, 8))
    for s in spec.get('segments') or []:
        a, b = fr(*s['from']), fr(*s['to'])
        parts.append(_line(a, b, 2.6 if not s.get('dash') else 1.5, '7 5' if s.get('dash') else '')); ink += _segment_pts(a, b)
        for end, p in zip(s.get('ends') or [], (a, b)):
            if end in ('open', 'closed'): later.append(_dot(p, end))
        if s.get('label'):
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            labels.append(_lab_side(s['label'], m[0], m[1], s.get('label_side', 'up'), 26, 8))
    for pt in spec.get('points') or []:
        p = fr(*pt['at'])
        later.append(_dot(p, 'open' if pt.get('open') else 'closed'))
        if pt.get('label'): labels.append(_lab_side(pt['label'], p[0], p[1], pt.get('side', 'up'), 26, 10))
    for text, p, ways in marks: labels.append(_mark(text, p, ways, ink, labels, box))
    for text, picks, i in named:
        others = [pts for j, pts in enumerate(curve_ink) if j != i]
        labels.append(_place(text, picks, ink, labels, box, curve_ink[i], others))
    parts.extend(later)
    return fr.B + 40


PROMPT = """
수학 그래프(앱이 식으로 계산해 그림, 좌표평면 위 함수·도형 그림은 SVG 규칙 대신 반드시 이 명세를 쓴다): 그림 자료는 image 블록 하나를 strict로 두고 image_locked 첫 글자부터 `도식: ` 뒤에 JSON 하나만 쓴다(image_creative·글씨 프롬프트는 빈 문자열). 글씨는 수식이면 $...$로 쓴다(예: "$y=f(x)$", "$a$", "$P$").
{"type":"function","view":[-2,4,-3,5],"curves":[{"expr":"x**2-2*x","domain":[-1,3],"ends":["closed","open"],"label":"$y=f(x)$"}],"x_ticks":[[2,"$2$"],[3,"$a$"]],"y_ticks":[[-1,"$-1$"]],"guides":[[1,-1]],"points":[{"at":[1,-1],"label":"$P$","side":"down"}],"asymptotes":[{"x":3}],"circles":[{"center":[0,0],"r":2}],"segments":[{"from":[0,0],"to":[2,2],"ends":["closed","open"]}],"fills":[{"curve":0,"from":0,"to":2}],"equal":false}
- view는 보일 범위 [x최소, x최대, y최소, y최대]다. 축은 원점을 지나고 화살표 끝에 $x$, $y$, 원점에 $O$를 앱이 쓴다.
- expr는 x 하나의 파이썬 식: + - * / **, sqrt, exp, log(x)(자연로그), log(x, 2)(밑 2), sin, cos, tan, abs, floor(가우스 기호 [x]), ceil, min, max, pi, e. 곱셈 기호 *를 빼지 않는다.
- 구간별로 정의된 함수, 닫힌구간·열린구간, 불연속인 함수(가우스 함수 등)는 구간마다 curve를 나누고 domain과 ends(구간 양 끝: closed 채운 점, open 빈 점, none 표시 없음)로 끝점을 표시한다. 합성함수·역함수·절댓값 함수도 식으로 쓴다(예: f(g(x))는 식을 대입해 한 식으로).
- 문항에서 쓰는 값만 x_ticks·y_ticks로 표시하고(수 대신 $a$ 같은 기호도 된다), 점에서 축으로 점선은 guides로 내린다. 점근선은 asymptotes, 넓이는 fills(with에 다른 곡선 번호를 주면 두 곡선 사이)로 칠한다.
- 원·정사각형처럼 가로세로 비가 중요하면 equal:true로 둔다.
- (가)(나) 두 그래프는 {"type":"panels","layout":"row","items":[{"type":"function",…,"caption":"(가)"},{"type":"function",…,"caption":"(나)"}]}로 놓는다.
- 그래프의 식·점·끝점이 문두 조건과 맞는지 review_note에 적는다. 정답에 쓰이는 값(극값, 교점 좌표 등)을 문항이 묻는다면 그 값을 눈금으로 드러내지 않는다.
"""
