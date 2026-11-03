# -*- coding: utf-8 -*-
"""문항 카드(.xlsx) → 학교 양식 기반 한글 문항지(.hml) 생성

  사용법:  python3 tools/gen.py [문항카드.xlsx] [출력.hml]
  기본값:  input/item-ideas 의 최신 xlsx  →  output/items/문항지_학교양식.hml
  ※ 자세한 절차와 함정은 instructions/HWPML-문항지-생성-지침.md 참조
"""
import io, os, re, sys, glob, copy, openpyxl, xml.etree.ElementTree as ET
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from metrics import metrics as eq_metrics
from hwp_equation import EquationConversionError, latex_to_hwp
from app.mathtext import math_segments

TPL_PATH = os.path.join(ROOT, 'templates', '학교양식_예시.hml')
if not os.path.exists(TPL_PATH):
    sys.exit(f"학교 양식 예시 파일이 없습니다: {TPL_PATH}\n"
             "양식 파일 없이는 서식을 맞출 수 없습니다. 지침 §1 참조.")
with io.open(TPL_PATH, encoding='utf-8-sig') as template_file:
    TPL = template_file.read()
# 한글을 글자 단위로 끊지 않는다. 줄은 어절(띄어쓰기) 단위로만 넘어간다.
HEAD = TPL[TPL.index('<HEAD '):TPL.index('</HEAD>')+7].replace('BreakNonLatinWord="true"', 'BreakNonLatinWord="false"')
TROOT = ET.fromstring(TPL)
TP = TROOT.find('.//SECTION').findall('P')
SECDEF = copy.deepcopy(TP[0].find('TEXT/SECDEF'))
# 표 양식 원본: 첫 문단(구역 정의·머리말·꼬리말) 뒤에 한 문단씩 (tools/make_school_template.py 의 ORDER)
SK = {name: TP[i + 1].find('.//TABLE') for i, name in enumerate(
    ['짧은', '중간', '긴', '짝2', '짝3', '보기', '보기짧은', '박스', '조건', '지적', '확인', '데이터'])}
CS_BODY, CS_NUM, CS_BOLD, CS_SET = '26', '25', '31', '39'   # 본문 11pt, 번호 13pt 굵게 기울임, 굵게, 세트 머리글 13pt 굵게
TABLE_KEEP_ROWS = 12                     # 자료 표가 이보다 길면 단에서 나뉘도록 둔다
PAIR_COL = {'짝2': 4800, '짝3': 2800}    # 짝짓기 답지 칸에서 한 줄에 들어가는 글자 폭. 넘치면 글자 중간에서 끊긴다
CS_UNDER = '42'                          # 본문 + 실선 밑줄
UNDERLINED = {'26': '42', '28': '42', '88': '42', '92': '93', '94': '95'}
PASSAGE_CS = {'11': '26', '10.5': '92', '10': '94'}   # 지문이 많은 과목은 0.5~1pt 줄일 수 있다 (원안지 안내)
# ── 정답 강조는 한글의 '형광펜'(MARKPEN)으로 한다 ──────────────
#    글자 음영(CHARSHAPE ShadeColor)을 쓰면 인쇄할 때 그대로 찍혀 나온다.
#    형광펜은 화면에만 보이고 인쇄되지 않으므로, 교사용 파일을 그대로 출력해도 된다.
HL_COLOR = '65535'                       # 노랑 (0x00FFFF, BGR)

def markpen(text_el, color=HL_COLOR):
    """<CHAR>③</CHAR> → <CHAR><MARKPENBEGIN Color=".."/>③<MARKPENEND/></CHAR>"""
    for ch in text_el.iter('CHAR'):
        txt = ch.text or ''
        if not txt.strip():
            continue
        ch.text = None
        b = ET.SubElement(ch, 'MARKPENBEGIN', {'Color': color})
        b.tail = txt
        ET.SubElement(ch, 'MARKPENEND')

PS_ITEM, PS_NORM, PS_CENTER, PS_RIGHT = '46', '1', '20', '27'
_IID = [1200000000]

# ── LaTeX → 한글 수식 스크립트 ───────────────────────────────
def eqscript(s):
    return latex_to_hwp(s)

def E_eq(script):
    w, h, b = eq_metrics(script)
    _IID[0] += 1
    e = ET.Element('EQUATION', {'BaseLine': str(b), 'BaseUnit': '1100', 'LineMode': 'false',
                                'TextColor': '0', 'Version': 'Equation Version 60'})
    so = ET.SubElement(e, 'SHAPEOBJECT', {'InstId': str(_IID[0]), 'Lock': 'false',
                                          'NumberingType': 'Equation', 'TextFlow': 'BothSides',
                                          'TextWrap': 'Square', 'ZOrder': str(_IID[0] % 1000)})
    ET.SubElement(so, 'SIZE', {'Height': str(h), 'HeightRelTo': 'Absolute', 'Protect': 'false',
                               'Width': str(w), 'WidthRelTo': 'Absolute'})
    ET.SubElement(so, 'POSITION', {'AffectLSpacing': 'false', 'AllowOverlap': 'false',
        'FlowWithText': 'true', 'HoldAnchorAndSO': 'false', 'HorzAlign': 'Left', 'HorzOffset': '0',
        'HorzRelTo': 'Para', 'TreatAsChar': 'true', 'VertAlign': 'Top', 'VertOffset': '0',
        'VertRelTo': 'Para'})
    ET.SubElement(so, 'OUTSIDEMARGIN', {'Bottom': '0', 'Left': '0', 'Right': '0', 'Top': '0'})
    ET.SubElement(e, 'SCRIPT').text = script
    return e

# ── 텍스트($수식$ 포함) → TEXT 요소 목록 ────────────────────
def runs(line, cs=CS_BODY):
    # [[구절]] in a passage is printed underlined (㉠·ⓐ marks the questions point at).
    if '[[' in line and cs in UNDERLINED:
        out = []
        for i, part in enumerate(re.split(r'\[\[(.+?)\]\]', line)):
            if part: out += runs(part, UNDERLINED[cs] if i % 2 else cs)
        return out or runs('', cs)
    out = []; buf = ''
    for kind, part in math_segments(line):
        if kind == 'math':
            if buf:
                t = ET.Element('TEXT', {'CharShape': cs}); ET.SubElement(t, 'CHAR').text = buf
                out.append(t); buf = ''
            t = ET.Element('TEXT', {'CharShape': cs}); t.append(E_eq(eqscript(part)))
            out.append(t)
        else: buf += part
    if buf or not out:
        t = ET.Element('TEXT', {'CharShape': cs}); ET.SubElement(t, 'CHAR').text = buf
        out.append(t)
    return out

# ── 의미 단위 줄나눔 ─────────────────────────────────────────
# 줄은 어절에서만 넘어간다. 줄 끝 어절이 한두 글자만 넘치면 그 줄의 자간을 줄여 넣고,
# 많이 넘치면 어절을 다음 줄로 보내고 남은 줄의 자간을 넓힌다. 폭은 추정이므로 어긋나도
# 한글이 어절 단위로 다시 넘길 뿐 낱말이 잘리지는 않는다.
ADVANCE = {' ': 550, '.': 264, ',': 264, '?': 564, '!': 360, '(': 432, ')': 408, '[': 408, ']': 384, '<': 805, '>': 805,
           ':': 300, ';': 324, '-': 624, '‘': 252, '’': 252, '“': 492, '”': 480, '/': 432, '%': 1009, '+': 624, '=': 624,
           '_': 552, '&': 901, '*': 576, '#': 492, '@': 1021, "'": 252, '"': 492,
           **dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ', (877, 769, 769, 817, 745, 721, 817, 865, 372, 504, 865, 708, 1057, 865, 817, 696, 829, 781, 708, 853, 853, 865, 1141, 829, 841, 660))),
           **dict(zip('abcdefghijklmnopqrstuvwxyz', (564, 612, 528, 600, 528, 384, 649, 624, 300, 348, 612, 300, 937, 624, 564, 588, 612, 444, 528, 396, 612, 649, 925, 649, 624, 528))),
           **{d: 550 for d in '0123456789'}}          # 한양신명조 11pt 실측 (한글 PDF, hwpunit). 없는 글자는 전각.
SQUEEZE_MAX, WIDEN_MAX, FIT_MARGIN = 6, 5, 120      # 줄일 자간 한도(%), 넓힐 자간 한도(%), 추정 오차 여유
COLUMN_W = 31041                                    # 2단 한 단의 폭
ITEM_HANG = 1000                                    # 문항 문단 둘째 줄부터 들여 쓰는 폭
# 칸 안에서 글이 실제로 차지하는 폭 (한글 PDF 실측, hwpunit).
BOX_W, BOGI_W, COND_W, LONG_W = 30600, 28000, 29800, 29400
CHARS = {c.get('Id'): c for c in TROOT.find('.//CHARSHAPELIST')}
PARAS = {p.get('Id'): p for p in TROOT.find('.//PARASHAPELIST')}
_SPACED, _KEEP = {}, {}
_CENTERED = set()

def font_size(cs): return int(CHARS[cs].get('Height'))

def base_spacing(cs): return int(CHARS[cs].find('CHARSPACING').get('Hangul'))

def spaced(cs, pct):
    """같은 글자 모양에 자간만 pct% 더한 글자 모양 번호. 머리(HEAD)에는 build 끝에서 넣는다."""
    if not pct: return cs
    key = (cs, pct)
    if key not in _SPACED:
        shape = copy.deepcopy(CHARS[cs])
        shape.set('Id', str(max(int(i) for i in CHARS) + 1 + len(_SPACED)))
        node = shape.find('CHARSPACING')
        for lang in list(node.attrib): node.set(lang, str(int(node.get(lang)) + pct))
        _SPACED[key] = shape
    return _SPACED[key].get('Id')

def text_width(text, cs):
    # 자간은 글자마다 그 글자 폭의 비율로 줄고 는다 (실측).
    size, gap = font_size(cs), base_spacing(cs)
    return sum(ADVANCE.get(c, 1100) * size / 1100 for c in text) * (1 + gap / 100)

def _tokens(line, cs, style=''):
    """띄어쓰기로 나눈 어절 목록. 어절은 글자·수식 조각을 묶고, 뒤따르는 공백 폭을 따로 안다.
    glyphs 는 자간의 영향을 받는 글자 폭의 합이다(수식은 자간을 따르지 않는다)."""
    tokens = [dict(parts=[], width=0.0, glyphs=0, space=0.0)]
    for i, chunk in enumerate(re.split(r'\[\[(.+?)\]\]', line)):
        if not chunk: continue
        mark = 'u' if i % 2 else style
        for kind, part in math_segments(chunk):
            if kind == 'math':
                tokens[-1]['parts'].append(('math', part, mark)); tokens[-1]['width'] += eq_metrics(eqscript(part))[0]
                continue
            for piece in re.split(r'( +)', part.replace(r'\~', '∼').replace('~', '∼')):
                if not piece: continue
                if piece.isspace():
                    if tokens[-1]['parts'] and tokens[-1]['parts'][-1][0] == 'text': tokens[-1]['parts'][-1] = ('text', tokens[-1]['parts'][-1][1] + piece, tokens[-1]['parts'][-1][2])
                    else: tokens[-1]['parts'].append(('text', piece, mark))
                    tokens[-1]['space'] += text_width(piece, cs); tokens[-1]['glyphs'] += text_width(piece, cs)
                    tokens.append(dict(parts=[], width=0.0, glyphs=0, space=0.0))
                else:
                    tokens[-1]['parts'].append(('text', piece, mark)); tokens[-1]['width'] += text_width(piece, cs); tokens[-1]['glyphs'] += text_width(piece, cs)
    return [t for t in tokens if t['parts']]

def _lay_out(tokens, cs, first, rest, offset):
    """어절을 줄에 앉히고 줄마다 더할 자간(%)을 정한다. 마지막 줄은 그대로 둔다."""
    lines = []; line = []; used = offset; width = first - FIT_MARGIN
    def close(pct):
        nonlocal line, used, width
        lines.append((line, pct)); line = []; used = 0; width = rest - FIT_MARGIN
    for token in tokens:
        need = used + token['width']
        if need <= width or not line:
            line.append(token); used = need + token['space']; continue
        glyphs = sum(t['glyphs'] for t in line)
        over = need - width
        squeeze = int(over * 100 / (glyphs + token['glyphs'])) + 1
        if squeeze <= SQUEEZE_MAX:
            line.append(token); close(-squeeze)
        else:
            gap = width - (used - line[-1]['space'])
            close(min(WIDEN_MAX, int(gap * 0.7 * 100 / max(glyphs, 1))))
            line.append(token); used = token['width'] + token['space']
    if line: lines.append((line, 0))
    return lines

def _emit(lines, cs):
    out = []
    for tokens, pct in lines:
        for token in tokens:
            for kind, part, mark in token['parts']:
                base = UNDERLINED.get(cs, cs) if mark == 'u' else CS_BOLD if mark == 'b' else cs
                shape = spaced(base, pct)
                if kind == 'math':
                    t = ET.Element('TEXT', {'CharShape': shape}); t.append(E_eq(eqscript(part))); out.append(t)
                elif out and out[-1].get('CharShape') == shape and out[-1].find('CHAR') is not None and out[-1].find('EQUATION') is None:
                    out[-1].find('CHAR').text += part
                else:
                    t = ET.Element('TEXT', {'CharShape': shape}); ET.SubElement(t, 'CHAR').text = part; out.append(t)
    return out or runs('', cs)

def fit_runs(line, cs, first, rest=None, offset=0):
    """runs() 와 같되 줄이 의미 단위로 넘어가게 자간을 조정한다."""
    return _emit(_lay_out(_tokens(line, cs), cs, first, first if rest is None else rest, offset), cs)

def question_paragraphs(line, tag, ps, prefix=None, tag_bold=False):
    """발문 + 배점. 배점이 그 줄에 온전히 들어가면 잇고, 아니면 다음 줄에 오른쪽 맞춤으로 둔다."""
    p = ET.Element('P', {'ParaShape': ps, 'Style': '0'})
    offset = 0; rest = COLUMN_W
    if prefix:
        t = ET.SubElement(p, 'TEXT', {'CharShape': CS_NUM}); ET.SubElement(t, 'CHAR').text = prefix
        offset = text_width(prefix, CS_NUM); rest = COLUMN_W - ITEM_HANG
    words = _tokens(line, CS_BODY)
    if words:
        tail = words[-1]
        tail['parts'].append(('text', ' ', '')); tail['space'] += ADVANCE[' ']; tail['glyphs'] += ADVANCE[' ']
    mark = 'b' if tag_bold else ''
    width = text_width(tag, CS_BOLD if tag_bold else CS_BODY)
    glued = dict(parts=[('text', tag, mark)], width=width, glyphs=width, space=0.0)
    lines = _lay_out(words + [glued], CS_BODY, COLUMN_W, rest, offset)
    if lines[-1][0][0] is not glued:                    # 배점이 온전히 이어진다
        for t in _emit(lines, CS_BODY): p.append(t)
        return [p]
    # 배점이 줄을 넘어가면 어절만 앉히고 배점은 오른쪽 맞춤 줄로 뺀다.
    if words:
        words[-1]['parts'].pop(); words[-1]['space'] -= ADVANCE[' ']; words[-1]['glyphs'] -= ADVANCE[' ']
    for t in _emit(_lay_out(words, CS_BODY, COLUMN_W, rest, offset), CS_BODY): p.append(t)
    right = ET.Element('P', {'ParaShape': PS_RIGHT, 'Style': '0'})
    t = ET.SubElement(right, 'TEXT', {'CharShape': CS_BOLD if tag_bold else CS_BODY}); ET.SubElement(t, 'CHAR').text = tag
    return [p, right]

def mkP(line, ps=PS_NORM, cs=CS_BODY, prefix=None, fit=None):
    p = ET.Element('P', {'ParaShape': ps, 'Style': '0'})
    if prefix:
        t = ET.Element('TEXT', {'CharShape': CS_NUM}); ET.SubElement(t, 'CHAR').text = prefix
        p.append(t)
    if fit:
        for t in fit_runs(line, cs, *fit, offset=text_width(prefix, CS_NUM) if prefix else 0): p.append(t)
    else:
        for t in runs(line, cs): p.append(t)
    return p

def split_question(text):
    """발문 칸에 상황 설명과 묻는 문장이 함께 있으면 나눈다. 묻는 문장은 줄을 바꿔 인쇄한다(글자는 그대로)."""
    breaks = list(re.finditer(r'(?<=다\.)\s+', text))
    if breaks and text.rstrip().endswith(('?', '시오.')):
        return text[:breaks[-1].start()].strip(), text[breaks[-1].end():].strip()
    return '', text

def is_blank(p):
    return not ''.join(p.itertext()).strip() and p.find('.//TABLE') is None and p.find('.//SECDEF') is None and p.find('.//EQUATION') is None

def set_cell(cell, line, force_cs=None, hl=False, fit=None):
    """셀 문단의 내용을 교체 (문단모양·문자모양은 원본 유지)"""
    pl = cell.find('PARALIST')
    p0 = pl.find('P')
    ps = p0.get('ParaShape'); st = p0.get('Style')
    ts = p0.findall('TEXT')
    main = next((t for t in ts if (t.findtext('CHAR') or '').strip()), None)
    if main is None:
        main = ts[0] if ts else None
    cs = force_cs or (main.get('CharShape') if main is not None else CS_BODY)
    for p in list(pl): pl.remove(p)
    np = ET.SubElement(pl, 'P', {'ParaShape': ps, 'Style': st})
    for t in (fit_runs(line, cs, *fit) if fit else runs(line, cs)):
        if hl: markpen(t)
        np.append(t)

def clone(kind):
    t = copy.deepcopy(SK[kind])
    so = t.find('SHAPEOBJECT')
    if so is not None:
        _IID[0] += 1; so.set('InstId', str(_IID[0])); so.set('ZOrder', str(_IID[0] % 1000))
    return t

def cells_of(tb):
    return [c for row in tb.findall('ROW') for c in row.findall('CELL')]

# ── 표 생성기 ────────────────────────────────────────────────
IDX = {   # 표 양식별 [번호칸], [내용칸]
 '짧은': ([1,3,5,7,9], [[2],[4],[6],[8],[10]]),
 '중간': ([1,3,5,8,10], [[2],[4],[6],[9],[11]]),
 '긴':   ([1,4,7,10,13], [[2],[5],[8],[11],[14]]),
 '짝2':  ([9,13,17,21,25], [[10,11],[14,15],[18,19],[22,23],[26,27]]),
 '짝3':  ([11,16,21,26,31], [[12,13,14],[17,18,19],[22,23,24],[27,28,29],[32,33,34]]),
}
HDR = {'짝2': [2,3,6,7], '짝3': [2,3,4,7,8,9]}
BLANK = {'짝2': [29,30,31], '짝3': [36,37,38,39]}
NUM = '①②③④⑤'


def _txt_w(s):
    """답지 한 칸의 렌더 폭 추정 (한글 11pt 기준)"""
    w = 0.0
    for kind, part in math_segments(s):
        if kind == 'math':
            w += eq_metrics(eqscript(part))[0]
        else:
            for c in part.replace(r'\~', '∼').replace('~', '∼'):
                w += 1100 if ord(c) > 0x2000 else (550 if c.isascii() else 1100)
    return w

def stack_pairs(kind, header, rows):
    """짝짓기 칸에서 줄이 바뀌면 글자가 끊긴다. 그럴 때는 2단 배치를 풀어 머리글 아래에 다섯 줄로 쌓는다(평가원 요약문 선지 꼴)."""
    if kind not in PAIR_COL or max(_txt_w(c) for r in [*rows, header or []] for c in r) <= PAIR_COL[kind]: return kind
    return '짝세로'

def stacked_pair_table(header, rows, ans=None):
    """머리글 한 줄과 ①~⑤ 다섯 줄. 칸 모양은 짝짓기 양식의 칸을 그대로 쓴다."""
    columns = len(rows[0]); source = '짝3' if columns == 3 else '짝2'
    tb = clone(source); cells = cells_of(tb); numbers, contents = IDX[source]
    num_cell, text_cell, head_cell = cells[numbers[0]], cells[contents[0][0]], cells[HDR[source][0]]
    total = sum(int(c.get('Width')) for c in tb.findall('ROW')[1].findall('CELL'))
    num_w = int(num_cell.get('Width')); text_w = (total - num_w) // columns
    def cell(proto, row, col, width, text, hl=False):
        c = copy.deepcopy(proto)
        c.attrib.update(RowAddr=str(row), ColAddr=str(col), Width=str(width), RowSpan='1', ColSpan='1')
        set_cell(c, text, hl=hl)
        return c
    for old in tb.findall('ROW'): tb.remove(old)
    top = ET.SubElement(tb, 'ROW')
    top.append(cell(text_cell, 0, 0, num_w, ''))
    for j in range(columns):
        top.append(cell(head_cell, 0, j + 1, text_w, header[j] if header and j < len(header) else ''))
    for r, values in enumerate(rows):
        row = ET.SubElement(tb, 'ROW')
        row.append(cell(num_cell, r + 1, 0, num_w, NUM[r], hl=bool(ans and r == ans - 1)))
        for j in range(columns):
            row.append(cell(text_cell, r + 1, j + 1, text_w, values[j] if j < len(values) else ''))
    tb.set('RowCount', str(len(rows) + 1)); tb.set('ColCount', str(columns + 1))
    return tb

def pick_kind(kind, rows):
    """짧은/중간/긴 은 내용 폭에 맞춰 자동 선택 (짝짓기형은 그대로)"""
    if kind in ('짝2', '짝3'): return kind
    mx = max(_txt_w(c) for r in rows for c in r)
    # 분수가 든 답지는 세로로 커서 '짧은' 표에 넣으면 잘린다 → 최소 '중간'
    has_frac = any(' over ' in eqscript(m) for r in rows for c in r
                   for m in re.findall(r'\$([^$]+)\$', c))
    if mx <= 3700 and not has_frac: return '짧은'
    if mx <= 7200:  return '중간'
    return '긴'

def answer_table(kind, rows, header=None, ans=None):
    """rows = [(내용,) …] 또는 [(c1,c2), …] / header = ['A','B'] 등"""
    tb = clone(kind); cs = cells_of(tb)
    ni, ci = IDX[kind]
    if header and kind in HDR:
        h = HDR[kind]; k = len(header)
        for j, cellidx in enumerate(h): set_cell(cs[cellidx], header[j % k])
    for r in range(5):
        set_cell(cs[ni[r]], NUM[r], hl=bool(ans and r == ans - 1))
        for j, cellidx in enumerate(ci[r]):
            set_cell(cs[cellidx], rows[r][j] if j < len(rows[r]) else '', fit=(LONG_W,) if kind == '긴' else None)
    for b in BLANK.get(kind, []): set_cell(cs[b], '')
    return tb

MARKS = ['ㄱ. ', 'ㄴ. ', 'ㄷ. ', 'ㄹ. ', 'ㅁ. ', 'ㅂ. ']

def bogi_table(items):
    """<보 기> 박스. 네 개의 짧은 보기는 2칸씩, 나머지는 한 줄에 하나씩. 박스 폭은 양식 그대로 둔다."""
    if len(items) == 4 and max(_txt_w(x) for x in items) <= 11000:
        tb = clone('보기짧은'); cs = cells_of(tb)
        for j, (mark, body) in enumerate(((6, 7), (8, 9), (12, 13), (14, 15))):
            set_cell(cs[mark], MARKS[j].strip()); set_cell(cs[body], items[j])
        return tb
    tb = clone('보기')
    rows = tb.findall('ROW')                 # 0·1 제목, 2~5 보기(양옆 여백 칸이 세로 병합), 6 아래 여백
    side = [c for c in rows[2].findall('CELL') if int(c.get('RowSpan') or 1) > 1]
    while len(rows) - 3 > len(items):
        tb.remove(rows[-2]); rows = tb.findall('ROW')
    while len(rows) - 3 < len(items):
        tb.insert(list(tb).index(rows[-1]), copy.deepcopy(rows[3])); rows = tb.findall('ROW')
    for ri, row in enumerate(rows):
        for c in row.findall('CELL'): c.set('RowAddr', str(ri))
    tb.set('RowCount', str(len(rows)))
    for c in side: c.set('RowSpan', str(len(items)))
    for j, row in enumerate(rows[2:-1]):
        cells = [c for c in row.findall('CELL') if int(c.get('RowSpan') or 1) == 1]
        for cell in cells: cell.set('Height', '1666')
        set_cell(cells[0], MARKS[j].strip()); set_cell(cells[1], items[j], fit=(BOGI_W,))
        if r'\frac' in items[j]:
            for cell in cells: _CENTERED.add(id(cell.find('PARALIST')))
    for c in side: c.set('Height', str(1666 * len(items)))
    return tb

BOX_KEEP_CHARS = 700      # 이보다 긴 글상자는 단 하나를 넘을 수 있어 나뉘게 둔다

def box_table(lines, cs_body=None, source='', keep=False):
    """지문 박스 — 양식처럼 첫 줄에 들여쓰기(작은 글자) + 본문. 빈 줄은 연·문단 구분으로 남긴다.
    keep: 문항 자료처럼 짧은 글상자는 단에 걸쳐 나뉘지 않게 글자처럼 취급한다."""
    tb = clone('박스'); cs = cells_of(tb)
    pl = cs[2].find('PARALIST'); p0 = pl.find('P')
    ps, st = p0.get('ParaShape'), p0.get('Style')
    ts = p0.findall('TEXT')
    cs_indent = ts[0].get('CharShape') if ts else CS_BODY          # 들여쓰기용(작은 글자)
    main = next((t for t in ts if (t.findtext('CHAR') or '').strip()), None)
    cs_body = cs_body or (main.get('CharShape') if main is not None else CS_BODY)   # 본문
    for p in list(pl): pl.remove(p)
    for k, ln in enumerate(lines):
        if re.fullmatch(r'- .+ -', ln.strip()):      # 출처 줄
            pl.append(mkP(ln.strip(), PS_RIGHT, cs_body)); continue
        np = ET.SubElement(pl, 'P', {'ParaShape': ps, 'Style': st})
        if k == 0:
            ti = ET.SubElement(np, 'TEXT', {'CharShape': cs_indent})
            ET.SubElement(ti, 'CHAR').text = '  '
        for t in fit_runs(ln, cs_body, BOX_W, offset=text_width('  ', cs_indent) if k == 0 else 0): np.append(t)
    if source:
        pl.append(mkP(f'- {source} -', PS_RIGHT, cs_body))
    # 양식의 칸 높이는 예시 글 기준이다. 짧은 글에 빈 줄이 남지 않게 줄이면 한글이 내용만큼 늘린다.
    for cell in (cs[1], cs[2], cs[3]): cell.set('Height', '1000')
    if keep and sum(len(x) for x in lines) <= BOX_KEEP_CHARS: return tb
    # 쪽을 넘는 긴 지문도 잘리지 않게 글자처럼 취급하지 않고 표 안에서 나눈다.
    tb.find('SHAPEOBJECT/POSITION').set('TreatAsChar', 'false')
    tb.set('PageBreak', 'Cell')
    return tb

def condition_table(lines):
    """서답형 답안 조건 <조 건> 박스. 줄마다 ◈ 를 붙인다."""
    tb = clone('조건'); cs = cells_of(tb)
    pl = cs[6].find('PARALIST'); p0 = pl.find('P')
    ps, st = p0.get('ParaShape'), p0.get('Style')
    for p in list(pl): pl.remove(p)
    for ln in lines:
        np = ET.SubElement(pl, 'P', {'ParaShape': ps, 'Style': st})
        for t in fit_runs('◈ ' + ln.lstrip('◈ ').strip(), '28', COND_W): np.append(t)
    return tb

def end_tables(school, has_subjective):
    """마지막 쪽 오른쪽 아래: 지적소유권 표(학교명이 있을 때) + 확인 사항 표."""
    PAGE_W, BODY_BOTTOM, RIGHT_MARGIN, COLUMN = 72852, 94676, 4251, 31041
    out = []
    check = clone('확인')
    cell = check.find('ROW/CELL/PARALIST')
    if not has_subjective:
        for p in list(cell):
            if ''.join(p.itertext()).strip().startswith('서답형'): cell.remove(p)
    tables = [check]
    if school:
        own = clone('지적')
        for ch in own.iter('CHAR'):
            if ch.text: ch.text = ch.text.replace('{학교명}', school)
        tables.insert(0, own)
    y = BODY_BOTTOM
    placed = []
    for tb in reversed(tables):
        height = int(tb.find('SHAPEOBJECT/SIZE').get('Height')) - (0 if has_subjective or tb is not check else 1200)
        y -= height + 280
        pos = tb.find('SHAPEOBJECT/POSITION')
        pos.attrib.update(TreatAsChar='false', HorzRelTo='Paper', VertRelTo='Paper', HorzAlign='Left', VertAlign='Top',
                          HorzOffset=str(PAGE_W - RIGHT_MARGIN - COLUMN), VertOffset=str(y), AllowOverlap='false', FlowWithText='false')
        placed.insert(0, tb)
    return [wrapP(tb) for tb in placed]

def section_start(school, subject):
    """구역 정의·2단·머리말·꼬리말이 든 첫 문단에 학교명과 과목명을 채운다."""
    p0 = copy.deepcopy(TP[0])
    for cell in p0.iter('CELL'):
        chars = [ch for ch in cell.iter('CHAR') if '{학교명}' in (ch.text or '')]
        for ch in chars: ch.text = ch.text.replace('{학교명}', school)
        if chars and not school: cell.set('BorderFill', '8')     # 학교명이 없으면 상자도 그리지 않는다
    for ch in p0.iter('CHAR'):
        if ch.text and '{과목명}' in ch.text: ch.text = ch.text.replace('{과목명}', subject)
    return p0

def table_widths(rows, columns, total):
    """칸 폭을 글자 양에 맞춘다. 먼저 칸마다 가장 긴 낱말이 끊기지 않을 폭을 주고, 남는 폭은 줄이 많이 바뀌는 칸에 더 준다."""
    PAD = 1300                                # 칸 안쪽 여백
    cells = [[r[j] if j < len(r) else '' for r in rows] for j in range(columns)]
    low = [max(_txt_w(w) for c in col for w in (c.split() or [''])) + PAD for col in cells]
    high = [max(_txt_w(c) for c in col) + PAD for col in cells]
    if sum(low) >= total:
        widths = [total * n / sum(low) for n in low]
    elif sum(high) <= total:
        widths = [n + (total - sum(high)) / columns for n in high]
    else:
        widths = [a + (total - sum(low)) * (b - a) / (sum(high) - sum(low)) for a, b in zip(low, high)]
    widths = [int(w) for w in widths]
    widths[-1] = total - sum(widths[:-1])
    return widths

def data_table(rows, keep=False):
    """임의 행/열 표 — '데이터' 양식의 셀 속성을 그대로 사용.
    keep이면 짧은 표를 글자처럼 다뤄 단에서 나뉘지 않게 한다. 떠 있는 표는 문단 묶음(KeepWithNext)을 따르지 않는다."""
    proto = clone('데이터')
    pcell = copy.deepcopy(proto.findall('ROW')[0].findall('CELL')[0])
    R, C = len(rows), max(len(r) for r in rows)
    TOTW, RH = 30108, 1282
    ws = table_widths(rows, C, TOTW)
    tb = ET.Element('TABLE', {'BorderFill': '3', 'CellSpacing': '0', 'ColCount': str(C),
                              'PageBreak': 'Cell', 'RepeatHeader': 'true', 'RowCount': str(R)})
    _IID[0] += 1
    so = ET.SubElement(tb, 'SHAPEOBJECT', {'InstId': str(_IID[0]), 'Lock': 'false',
        'NumberingType': 'Table', 'TextWrap': 'TopAndBottom', 'ZOrder': str(_IID[0] % 1000)})
    ET.SubElement(so, 'SIZE', {'Height': str(RH*R + 566), 'HeightRelTo': 'Absolute',
        'Protect': 'false', 'Width': str(TOTW + 1230), 'WidthRelTo': 'Absolute'})
    ET.SubElement(so, 'POSITION', {'AffectLSpacing': 'false', 'AllowOverlap': 'false',
        'FlowWithText': 'true', 'HoldAnchorAndSO': 'false', 'HorzAlign': 'Left', 'HorzOffset': '0',
        'HorzRelTo': 'Para', 'TreatAsChar': 'true' if keep and R <= TABLE_KEEP_ROWS else 'false', 'VertAlign': 'Top', 'VertOffset': '0',
        'VertRelTo': 'Para'})
    ET.SubElement(so, 'OUTSIDEMARGIN', {'Bottom': '283', 'Left': '283', 'Right': '283', 'Top': '283'})
    ET.SubElement(tb, 'INSIDEMARGIN', {'Bottom': '141', 'Left': '510', 'Right': '510', 'Top': '141'})
    for ri, row in enumerate(rows):
        rw = ET.SubElement(tb, 'ROW')
        for ci in range(C):
            c = copy.deepcopy(pcell)
            c.set('ColAddr', str(ci)); c.set('RowAddr', str(ri))
            c.set('Width', str(ws[ci])); c.set('Height', str(RH))
            set_cell(c, row[ci] if ci < len(row) else '')
            rw.append(c)
    return tb

def wrapP(tb, ps=PS_NORM):
    p = ET.Element('P', {'ParaShape': ps, 'Style': '0'})
    t = ET.SubElement(p, 'TEXT', {'CharShape': CS_BODY})
    t.append(tb); ET.SubElement(t, 'CHAR').text = ''
    return p

def normalize_hml_char_tildes(section):
    """Normalize source tildes in visible HML text without touching equation scripts."""
    def source_text(value):
        return value.replace(r'\~', '∼').replace('~', '∼')

    def visit(node):
        if node.text:
            node.text = source_text(node.text)
        for child in node:
            visit(child)
            if child.tail:
                child.tail = source_text(child.tail)

    for char in section.iter('CHAR'):
        visit(char)

# ── 문항 데이터 파싱 ─────────────────────────────────────────
def detect_kind(n):
    """답지 첫 줄(머리글)이 2~3열로 갈라지면 짝2/짝3, 아니면 폭으로 자동 선택."""
    lines = [l for l in (n or '').split('\n') if l.strip()]
    if not lines: return '짧은'
    if lines[0].strip()[0] in NUM: return '짧은'
    parts = [x for x in re.split(r'\s*/\s*|\s{2,}', lines[0].strip()) if x.strip()]
    return {2: '짝2', 3: '짝3'}.get(len(parts), '짧은')

def split_answers(n, kind):
    lines = [l for l in n.split('\n') if l.strip()]
    ai = [i for i, l in enumerate(lines) if l.strip()[0] in NUM]
    header, body = None, None
    if len(ai) >= 5:
        if ai[0] > 0: header = lines[:ai[0]]
        body = [lines[i] for i in ai[:5]]
    else:                                   # 한 줄에 ①~⑤ 가 모두 있는 경우
        one = ' '.join(lines)
        parts = re.split(r'\s*(?=[①②③④⑤])', one)
        pre = [p for p in parts if p and p[0] not in NUM]
        header = pre or None
        body = [p for p in parts if p and p[0] in NUM][:5]
    ncol = {'짝2': 2, '짝3': 3}.get(kind, 1)
    rows = []
    for l in body:
        t = l.strip()[1:].strip()
        if ncol == 1: rows.append((t,))
        else:
            cols = re.split(r'\s*/\s*|\s{2,}', t)
            cols = [c.strip() for c in cols if c.strip()]
            while len(cols) < ncol: cols.append('')
            rows.append(tuple(cols[:ncol]))
    hdr = None
    if ncol > 1 and header:
        h = re.split(r'\s*/\s*|\s{2,}', ' '.join(header).strip())
        hdr = [x.strip() for x in h if x.strip()][:ncol]
    return hdr, rows

def split_bogi(m):
    m = m.strip()
    if '\n' not in m:
        for mk in 'ㄴㄷㄹㅁㅂ':
            m = re.sub(r'\s+(' + mk + r'\.)', '\n' + mk + '.', m)
    out = []
    for l in m.split('\n'):
        l = l.strip()
        if re.match(r'^[ㄱㄴㄷㄹㅁㅂ]\.', l): out.append(l[2:].strip())
    return out

def pipe_cells(line):
    """표 한 줄을 칸으로 나눈다. 수식 안의 | (절댓값 등)는 칸 구분이 아니다."""
    cells, cell, in_math = [], '', False
    for ch in line.strip().strip('|'):
        if ch == '$': in_math = not in_math
        if ch == '|' and not in_math: cells.append(cell.strip()); cell = ''
        else: cell += ch
    return cells + [cell.strip()]

def parse_pipe(k):
    rows = []
    for l in k.split('\n'):
        s = l.strip()
        if not s.startswith('|'): continue
        cs = pipe_cells(s)
        if all(re.fullmatch(r':?-{2,}:?', c) for c in cs): continue
        rows.append(cs)
    return rows

# ── 본문 생성 ────────────────────────────────────────────────
# A label that only names the block's kind ("그림", "자료 표", "그림 1") is an app-side tag, not a printed caption;
# only labels the question refers to, such as "(가)" or "[실험 Ⅰ]", go on the paper.
KIND_LABEL = re.compile(r'^[\s(（<〈\[]*(자료\s*)?(그림|이미지|표|자료\s*표|글상자|자료)(\s*\d+)?\s*[)）>〉\]]*$')

def printed_label(label):
    return '' if KIND_LABEL.fullmatch(label) else label

def passage_set_paragraphs(info, passage_size='11'):
    """A passage set prints once before its first question: 【 n∼m 】 and each passage in a box."""
    a, b = info['range']
    label = f'【 {a}∼{b} 】' if a != b else f'【 {a} 】'
    passages = info['passages']
    labels = [p.get('label') or '' for p in passages]
    what = '(가)와 (나)를' if len(passages) == 2 and labels == ['(가)', '(나)'] else '다음 글을'
    head = ET.Element('P', {'ParaShape': PS_NORM, 'Style': '0'})
    t = ET.SubElement(head, 'TEXT', {'CharShape': CS_SET}); ET.SubElement(t, 'CHAR').text = label
    t = ET.SubElement(head, 'TEXT', {'CharShape': CS_BOLD}); ET.SubElement(t, 'CHAR').text = f'{what} 읽고 물음에 답하시오.'
    out = [head]
    cs = PASSAGE_CS.get(str(passage_size), CS_BODY)
    for p in passages:
        lines = str(p.get('content') or '').split('\n')
        if p.get('label'): lines[0] = f"{p['label']} {lines[0]}"
        out.append(wrapP(box_table(lines, cs, p.get('source') or '')))
        out.append(mkP(''))                        # 박스와 문항 사이 한 줄
    return out

def head_with_spacing():
    """줄나눔이 쓴 자간 글자 모양과 문항을 묶는 문단 모양을 머리의 목록에 더한다."""
    head = HEAD
    if _SPACED:
        extra = ''.join(ET.tostring(shape, encoding='unicode') for shape in _SPACED.values())
        head = head.replace('</CHARSHAPELIST>', extra + '</CHARSHAPELIST>')
        head = re.sub(r'<CHARSHAPELIST Count="\d+"', f'<CHARSHAPELIST Count="{len(CHARS) + len(_SPACED)}"', head)
    if _KEEP:
        extra = ''.join(ET.tostring(shape, encoding='unicode') for shape in _KEEP.values())
        head = head.replace('</PARASHAPELIST>', extra + '</PARASHAPELIST>')
        head = re.sub(r'<PARASHAPELIST Count="\d+"', f'<PARASHAPELIST Count="{len(PARAS) + len(_KEEP)}"', head)
    return head

def keep_together(paragraphs):
    """문항이 단이나 쪽에 걸쳐 잘리지 않게 마지막 문단만 빼고 다음 문단과 묶는다. 지문 박스는 길면 나뉘어야 하므로 묶지 않는다."""
    for p in paragraphs[:-1]:
        ps = p.get('ParaShape')
        if ps not in _KEEP:
            shape = copy.deepcopy(PARAS[ps]); shape.set('Id', str(max(int(i) for i in PARAS) + 1 + len(_KEEP)))
            shape.set('KeepWithNext', 'true'); shape.set('KeepLines', 'true'); shape.set('BreakNonLatinWord', 'false'); _KEEP[ps] = shape
        p.set('ParaShape', _KEEP[ps].get('Id'))

def exam_dir(name=None):
    """회차 폴더를 고른다. 이름을 주지 않으면 exams/ 안에서 가장 최근에 손댄 폴더."""
    base = os.path.join(ROOT, 'exams')
    if name:
        d = os.path.join(base, name)
        if not os.path.isdir(d): sys.exit("회차 폴더가 없습니다: " + d)
        return d
    cands = [os.path.join(base, x) for x in os.listdir(base)
             if os.path.isdir(os.path.join(base, x)) and not x.startswith('_')] if os.path.isdir(base) else []
    if not cands: sys.exit("exams/ 아래에 회차 폴더가 없습니다. tools/new_exam.py 로 만드십시오.")
    return max(cands, key=os.path.getmtime)

def default_src(exam):
    c = sorted(glob.glob(os.path.join(exam, '02_card', '*.xlsx')), key=os.path.getmtime, reverse=True)
    c = [x for x in c if not os.path.basename(x).startswith('~$')]
    return c[0] if c else None

def build(src=None, out=None, exam=None, title=None, records=None, school='', subject='', passage_size='11'):
    exam = exam or exam_dir(exam)
    src = src or default_src(exam)
    out = out or os.path.join(exam, '03_paper', '문항지.hml')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    _SPACED.clear(); _KEEP.clear()
    print("  회차:", os.path.basename(exam))
    if not src: sys.exit("문항 카드(.xlsx)를 찾지 못했습니다.")
    print("  카드:", os.path.relpath(src, ROOT))
    print("  양식:", os.path.relpath(TPL_PATH, ROOT))
    ws = openpyxl.load_workbook(src, data_only=True)['문항카드 생성'] if records is None else None
    body = []
    body.append(section_start(school, subject or title or os.path.basename(exam)))
    has_subjective = False
    if records is None:
        records = [[ws.cell(r, c).value for c in range(1, 19)] + [ws.cell(r, 34).value]
                   for r in range(11, min(ws.max_row, 110) + 1)
                   if any(ws.cell(r, c).value for c in (9, 10, 11, 12, 13, 14))]
    for record in records:
        g = lambda c: record[c-1] if record[c-1] is not None else ''
        no, pt = g(2), g(15)
        J, K, L, M, N = [str(g(c)).strip() for c in (10, 11, 12, 13, 14)]
        head_done = False
        set_info = record[21] if len(record) > 21 else None
        if set_info:
            body.extend(passage_set_paragraphs(set_info, passage_size))
        written = record[22] if len(record) > 22 else None      # 서답형: {'order','kind','conditions','partial'}
        number = f"서답형 {written['order']}." if written else f'{no}.'
        has_subjective = has_subjective or bool(written)
        if not J or J == '없음.':
            J, L = split_question(L)
        start = len(body)
        J, L = J.replace('〈보기〉', '<보기>'), L.replace('〈보기〉', '<보기>')   # 양식 표기
        if J and J != '없음.':
            first_line, *more = [x.strip() for x in J.split('\n') if x.strip()]
            body.append(mkP(' ' + first_line, PS_ITEM, prefix=number, fit=(COLUMN_W, COLUMN_W - ITEM_HANG))); head_done = True
            for line in more: body.append(mkP(line, PS_NORM, fit=(COLUMN_W,)))
        # 양식의 순서: 문두가 없으면 발문·배점이 먼저, 자료는 그 뒤. 문두가 있으면 문두 → 자료 → 발문.
        def question_line():
            if not L or L == '없음.': return
            pre = None if head_done else number
            ps_line = PS_ITEM if pre else PS_NORM
            text = (' ' if pre else '') + L
            if written:
                score = f"{float(pt):.1f}" if pt not in ('', None) else ''
                extra = ', 부분점수 있음.' if written.get('partial') else ''
                body.extend(question_paragraphs(text, f"[{written['kind']}-{score}점{extra}]", ps_line, pre, tag_bold=True))
            else:
                body.extend(question_paragraphs(text, f'[{pt}점]', ps_line, pre))
        if not head_done: question_line()
        material_data=record[20] if len(record)>20 else None
        if isinstance(material_data,str) and material_data.strip():
            material_data=json.loads(material_data)
        if material_data is not None:
            if not isinstance(material_data,list): raise ValueError(f'{no}번: 자료 블록은 배열이어야 합니다.')
            for block in material_data:
                kind=block.get('kind'); label=str(block.get('label') or '').strip(); content=str(block.get('content') or '').strip()
                if printed_label(label): body.append(mkP(label,PS_NORM,CS_NUM))
                if kind=='image':
                    mid=str(block.get('id') or '')
                    if not re.fullmatch(r'[a-f0-9]{16}',mid): raise ValueError(f'{no}번: 그림 자료 ID 오류')
                    body.append(mkP(f'〔그림 프롬프트 시작 · {no}번 · {mid}〕',PS_NORM,CS_NUM))
                    body.append(mkP(content or '그림 자료',PS_NORM))
                    body.append(mkP(f'〔그림 프롬프트 끝 · {no}번 · {mid}〕',PS_NORM,CS_NUM))
                elif kind=='text':
                    lines=[x for x in content.splitlines() if x.strip()]
                    if lines and lines[0].strip().startswith('(글상자'): lines=lines[1:]
                    body.append(wrapP(box_table(lines or [''], keep=True)))
                    body.append(mkP(''))
                elif kind=='table':
                    rows=parse_pipe(content)
                    if not rows: raise ValueError(f'{no}번: 표 자료에 Markdown 파이프 표가 없습니다.')
                    lines=[x.strip() for x in content.splitlines() if x.strip()]
                    first=next(i for i,x in enumerate(lines) if x.startswith('|'))
                    last=max(i for i,x in enumerate(lines) if x.startswith('|'))
                    for ln in lines[:first]: body.append(mkP(ln,PS_NORM,fit=(COLUMN_W,)))
                    body.append(wrapP(data_table(rows, keep=True)))
                    for ln in lines[last+1:]: body.append(mkP(ln,PS_NORM,fit=(COLUMN_W,)))
                    body.append(mkP(''))
                else: raise ValueError(f'{no}번: 알 수 없는 자료 유형입니다.')
        elif K and K != '없음.':
            kl = [x for x in K.split('\n') if x.strip()]
            if kl[0].strip().startswith('(글상자'):
                body.append(wrapP(box_table(kl[1:], keep=True)))
                body.append(mkP(''))
            elif any(x.strip().startswith('|') for x in kl):
                pre, tail, seen = [], [], False
                for x in kl:
                    t = x.strip()
                    if t.startswith('|'): seen = True; continue
                    if re.fullmatch(r'\(표\)|\(상자\)', t): continue
                    (tail if seen else pre).append(x)
                for ln in pre: body.append(mkP(ln, PS_NORM))
                body.append(wrapP(data_table(parse_pipe(K), keep=True)))
                body.append(mkP(''))
                for ln in tail: body.append(mkP(ln, PS_NORM))
            else:
                body.append(mkP(f'〔그림 프롬프트 시작 · {no}번〕', PS_NORM, CS_NUM))
                for ln in kl: body.append(mkP(ln, PS_NORM))
                body.append(mkP(f'〔그림 프롬프트 끝 · {no}번〕', PS_NORM, CS_NUM))
        if head_done: question_line()
        if written and written.get('conditions'):
            body.append(wrapP(condition_table(written['conditions'])))
        if M and M != '없음.':
            body.append(wrapP(bogi_table(split_bogi(M))))
        if N and N != '없음.':
            kind = detect_kind(N)
            hdr, rows = split_answers(N, kind)
            kind = stack_pairs(kind, hdr, rows)
            if kind == '짝세로':
                body.append(wrapP(stacked_pair_table(hdr, rows, ans=g(8))))
            else:
                kind = pick_kind(kind, rows)
                body.append(wrapP(answer_table(kind, rows, hdr, ans=g(8))))
        item = body[start:]
        while item and is_blank(item[-1]): item.pop()
        keep_together(item)       # 자료 뒤 빈 줄도 함께 묶어야 표 뒤에서 끊기지 않는다
        body.append(mkP(''))
    body = [p for i, p in enumerate(body) if not (is_blank(p) and i and is_blank(body[i - 1]))]   # 빈 줄이 겹치지 않게
    # 끝 표는 마지막 쪽 아래에 고정된다. 자리가 없어 다음 쪽으로 밀리면 마지막 문항도 함께 옮겨 표만 남은 쪽을 만들지 않는다.
    tail = len(body)
    while tail > 1 and is_blank(body[tail - 1]): tail -= 1
    # 확인 사항 표는 마지막 문단에 붙인다. 표만 든 문단이 따로 있으면 그 문단만 다음 쪽으로 밀려 표만 있는 쪽이 생긴다.
    closing = end_tables(school, has_subjective)
    if tail > 1:
        del body[tail:]
        for wrapped in closing:
            run = ET.SubElement(body[-1], 'TEXT', {'CharShape': CS_BODY})
            run.extend(list(wrapped.find('TEXT')))
    else:
        body.extend(closing)
    sec = ET.Element('SECTION', {'Id': '0'})
    for p in body: sec.append(p)
    # 모든 표의 셀 세로 정렬을 '위'로
    # ── 구조 검증: 표 칸 구조가 어긋나면 한글이 파일 자체를 열지 못한다 ──
    def check_tables(sec):
        bad = []
        for ti, tb in enumerate(sec.iter('TABLE')):
            rows = tb.findall('ROW')
            cc = int(tb.get('ColCount') or 0)
            if int(tb.get('RowCount') or 0) != len(rows):
                bad.append(f"표{ti}: RowCount {tb.get('RowCount')} != 실제 {len(rows)}")
            widths = set()
            for ri, row in enumerate(rows):
                cells = row.findall('CELL')
                span = sum(int(c.get('ColSpan') or 1) for c in cells)
                # 위 행에서 세로 병합으로 내려온 칸 수를 더한다
                carried = 0
                for rj in range(ri):
                    for c in rows[rj].findall('CELL'):
                        if int(c.get('RowSpan') or 1) > ri - rj:
                            carried += int(c.get('ColSpan') or 1)
                if span + carried != cc:
                    bad.append(f"표{ti} {ri}행: 열 합 {span}+병합 {carried} != ColCount {cc}")
                widths.add(sum(int(c.get('Width') or 0) for c in cells) +
                           sum(int(c.get('Width') or 0) for rj in range(ri)
                               for c in rows[rj].findall('CELL')
                               if int(c.get('RowSpan') or 1) > ri - rj))
                for c in cells:
                    if int(c.get('RowAddr') or -1) != ri:
                        bad.append(f"표{ti} {ri}행: RowAddr {c.get('RowAddr')} 불일치")
            if len(widths) > 1:
                bad.append(f"표{ti}: 행별 폭 합이 다름 {sorted(widths)}")
        return bad
    errs = check_tables(sec)
    if errs:
        print("\n[표 구조 오류] 한글이 열지 못하는 파일입니다. 저장하지 않았습니다.")
        for e in errs[:20]: print("  -", e)
        sys.exit(1)
    print(f"  표 구조 검증 통과: {len(list(sec.iter('TABLE')))}개")

    n = 0
    for p in body[1:]:                                   # 머리말·꼬리말은 양식 그대로 둔다
        for cell in p.iter('CELL'):
            for pl in cell.findall('PARALIST'):
                wanted = 'Center' if id(pl) in _CENTERED else 'Top'
                if pl.get('VertAlign') != wanted: pl.set('VertAlign', wanted); n += 1
    print(f"  셀 세로정렬 '위'로 변경: {n}칸")
    # HWP equation SCRIPT may use ASCII `~` as a Hancom spacing marker.
    # Normalize only visible CHAR content, preserving those generated markers.
    normalize_hml_char_tildes(sec)
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="no" ?>'
           f'<HWPML Style="embed" SubVersion="{TROOT.get("SubVersion")}" Version="{TROOT.get("Version")}">' + head_with_spacing() +
           '<BODY>' + ET.tostring(sec, encoding='unicode') + '</BODY><TAIL></TAIL></HWPML>')
    with io.open(out, 'w', encoding='utf-8') as output_file:
        output_file.write(xml)
    return xml

if __name__ == '__main__':
    # 사용법:  python tools/gen.py [회차폴더이름]
    #   회차폴더이름을 생략하면 exams/ 안에서 가장 최근에 손댄 폴더를 쓴다.
    a = [v for v in sys.argv[1:] if not v.startswith('-')]
    try:
        x = build(exam=exam_dir(a[0] if a else None))
    except EquationConversionError as exc:
        print(f"[수식 변환 오류] {exc}\n출력 파일을 갱신하지 않았습니다.", file=sys.stderr)
        sys.exit(2)
    print(f"생성 완료 {len(x):,} bytes | 수식 {x.count('<EQUATION')} | 표 {x.count('<TABLE')}"
          f" | 형광펜 {x.count('<MARKPENBEGIN')}")
    print("\n다음 단계: 한글에서 열고 tools/수식크기_재계산.py 를 실행하십시오.")
