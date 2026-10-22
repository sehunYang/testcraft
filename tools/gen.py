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
HEAD = TPL[TPL.index('<HEAD '):TPL.index('</HEAD>')+7]
TROOT = ET.fromstring(TPL)
TP = TROOT.find('.//SECTION').findall('P')
SECDEF = copy.deepcopy(TP[0].find('TEXT/SECDEF'))
SK = {  # 표 양식 원본
 '짧은': TP[26].find('.//TABLE'), '중간': TP[28].find('.//TABLE'), '긴': TP[30].find('.//TABLE'),
 '짝2': TP[32].find('.//TABLE'), '짝3': TP[34].find('.//TABLE'),
 '보기': TP[44].find('.//TABLE'), '박스': TP[40].find('.//TABLE'),
 '데이터': [t for t in TP[38].iter('TABLE')][1],
}
CS_BODY, CS_NUM, CS_EMPTY = '1', '3', '5'
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

PS_ITEM, PS_NORM = '2', '1'
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

def mkP(line, ps=PS_NORM, cs=CS_BODY, prefix=None):
    p = ET.Element('P', {'ParaShape': ps, 'Style': '0'})
    if prefix:
        t = ET.Element('TEXT', {'CharShape': CS_NUM}); ET.SubElement(t, 'CHAR').text = prefix
        p.append(t)
    for t in runs(line, cs): p.append(t)
    return p

def set_cell(cell, line, force_cs=None, hl=False):
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
    for t in runs(line, cs):
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
            set_cell(cs[cellidx], rows[r][j] if j < len(rows[r]) else '')
    for b in BLANK.get(kind, []): set_cell(cs[b], '')
    return tb

MARKS = ['ㄱ. ', 'ㄴ. ', 'ㄷ. ', 'ㄹ. ', 'ㅁ. ', 'ㅂ. ']

def bogi_table(items, percol=1):
    """percol개씩 한 줄에 넣는다. 표의 칸 구조는 양식 그대로 둔다(건드리면 한글이 파일을 거부한다)."""
    tb = clone('보기'); cs = cells_of(tb)
    MK, BD = [6, 9, 11], [7, 10, 12]          # ㄱ/ㄴ/ㄷ 줄의 기호칸·내용칸
    if percol <= 1:
        for j, body in enumerate(items[:3]):
            set_cell(cs[MK[j]], MARKS[j]); set_cell(cs[BD[j]], body)
        for j in range(len(items), 3):
            set_cell(cs[MK[j]], ''); set_cell(cs[BD[j]], '')
        return tb
    lines = []
    for i in range(0, len(items), percol):
        chunk = items[i:i + percol]
        lines.append('    '.join(MARKS[i + k] + chunk[k] for k in range(len(chunk))))
    for j in range(3):
        set_cell(cs[MK[j]], '')
        set_cell(cs[BD[j]], lines[j] if j < len(lines) else '')
    return tb

def box_table(lines):
    """지문 박스 — 템플릿처럼 첫 줄에 들여쓰기(작은 글자) + 본문(11pt)"""
    tb = clone('박스'); cs = cells_of(tb)
    pl = cs[2].find('PARALIST'); p0 = pl.find('P')
    ps, st = p0.get('ParaShape'), p0.get('Style')
    ts = p0.findall('TEXT')
    cs_indent = ts[0].get('CharShape') if ts else CS_BODY          # 들여쓰기용(작은 글자)
    main = next((t for t in ts if (t.findtext('CHAR') or '').strip()), None)
    cs_body = main.get('CharShape') if main is not None else CS_BODY   # 본문
    for p in list(pl): pl.remove(p)
    for k, ln in enumerate(lines):
        np = ET.SubElement(pl, 'P', {'ParaShape': ps, 'Style': st})
        if k == 0:
            ti = ET.SubElement(np, 'TEXT', {'CharShape': cs_indent})
            ET.SubElement(ti, 'CHAR').text = '  '
        for t in runs(ln, cs_body): np.append(t)
    return tb

def data_table(rows):
    """임의 행/열 표 — '데이터' 양식의 셀 속성을 그대로 사용"""
    proto = clone('데이터')
    pcell = copy.deepcopy(proto.findall('ROW')[0].findall('CELL')[0])
    R, C = len(rows), max(len(r) for r in rows)
    TOTW, RH = 30108, 1282
    ws = [TOTW // C] * C; ws[-1] = TOTW - sum(ws[:-1])
    tb = ET.Element('TABLE', {'BorderFill': '4', 'CellSpacing': '0', 'ColCount': str(C),
                              'PageBreak': 'Cell', 'RepeatHeader': 'true', 'RowCount': str(R)})
    _IID[0] += 1
    so = ET.SubElement(tb, 'SHAPEOBJECT', {'InstId': str(_IID[0]), 'Lock': 'false',
        'NumberingType': 'Table', 'TextWrap': 'TopAndBottom', 'ZOrder': str(_IID[0] % 1000)})
    ET.SubElement(so, 'SIZE', {'Height': str(RH*R + 566), 'HeightRelTo': 'Absolute',
        'Protect': 'false', 'Width': str(TOTW + 1230), 'WidthRelTo': 'Absolute'})
    ET.SubElement(so, 'POSITION', {'AffectLSpacing': 'false', 'AllowOverlap': 'false',
        'FlowWithText': 'true', 'HoldAnchorAndSO': 'false', 'HorzAlign': 'Left', 'HorzOffset': '0',
        'HorzRelTo': 'Para', 'TreatAsChar': 'false', 'VertAlign': 'Top', 'VertOffset': '0',
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

def parse_pipe(k):
    rows = []
    for l in k.split('\n'):
        s = l.strip()
        if not s.startswith('|'): continue
        cs = [c.strip() for c in s.strip('|').split('|')]
        if all(re.fullmatch(r':?-{2,}:?', c) for c in cs): continue
        rows.append(cs)
    return rows

# ── 본문 생성 ────────────────────────────────────────────────
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

def build(src=None, out=None, exam=None, title=None, records=None):
    exam = exam or exam_dir(exam)
    src = src or default_src(exam)
    out = out or os.path.join(exam, '03_paper', '문항지.hml')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    print("  회차:", os.path.basename(exam))
    if not src: sys.exit("문항 카드(.xlsx)를 찾지 못했습니다.")
    print("  카드:", os.path.relpath(src, ROOT))
    print("  양식:", os.path.relpath(TPL_PATH, ROOT))
    ws = openpyxl.load_workbook(src, data_only=True)['문항카드 생성'] if records is None else None
    body = []
    p0 = ET.Element('P', {'ParaShape': '0', 'Style': '0'})
    t0 = ET.SubElement(p0, 'TEXT', {'CharShape': CS_BODY})
    t0.append(copy.deepcopy(SECDEF)); ET.SubElement(t0, 'CHAR').text = ''
    body.append(p0)
    body.append(mkP(title or os.path.basename(exam), '0', CS_NUM))
    body.append(mkP(''))
    if records is None:
        records = [[ws.cell(r, c).value for c in range(1, 19)] + [ws.cell(r, 34).value]
                   for r in range(11, min(ws.max_row, 110) + 1)
                   if any(ws.cell(r, c).value for c in (9, 10, 11, 12, 13, 14))]
    for record in records:
        g = lambda c: record[c-1] if record[c-1] is not None else ''
        no, pt = g(2), g(15)
        J, K, L, M, N = [str(g(c)).strip() for c in (10, 11, 12, 13, 14)]
        head_done = False
        if J and J != '없음.':
            body.append(mkP(' ' + J, PS_ITEM, prefix=f'{no}.')); head_done = True
        material_data=record[20] if len(record)>20 else None
        if isinstance(material_data,str) and material_data.strip():
            material_data=json.loads(material_data)
        if material_data is not None:
            if not isinstance(material_data,list): raise ValueError(f'{no}번: 자료 블록은 배열이어야 합니다.')
            for block in material_data:
                kind=block.get('kind'); label=str(block.get('label') or '').strip(); content=str(block.get('content') or '').strip()
                if label: body.append(mkP(label,PS_NORM,CS_NUM))
                if kind=='image':
                    mid=str(block.get('id') or '')
                    if not re.fullmatch(r'[a-f0-9]{16}',mid): raise ValueError(f'{no}번: 그림 자료 ID 오류')
                    body.append(mkP(f'〔그림 프롬프트 시작 · {no}번 · {mid}〕',PS_NORM,CS_NUM))
                    body.append(mkP(content or '그림 자료',PS_NORM))
                    body.append(mkP(f'〔그림 프롬프트 끝 · {no}번 · {mid}〕',PS_NORM,CS_NUM))
                elif kind=='text':
                    lines=[x for x in content.splitlines() if x.strip()]
                    if lines and lines[0].strip().startswith('(글상자'): lines=lines[1:]
                    body.append(wrapP(box_table(lines or [''])))
                elif kind=='table':
                    rows=parse_pipe(content)
                    if not rows: raise ValueError(f'{no}번: 표 자료에 Markdown 파이프 표가 없습니다.')
                    body.append(wrapP(data_table(rows)))
                else: raise ValueError(f'{no}번: 알 수 없는 자료 유형입니다.')
        elif K and K != '없음.':
            kl = [x for x in K.split('\n') if x.strip()]
            if kl[0].strip().startswith('(글상자'):
                body.append(wrapP(box_table(kl[1:])))
            elif any(x.strip().startswith('|') for x in kl):
                pre, tail, seen = [], [], False
                for x in kl:
                    t = x.strip()
                    if t.startswith('|'): seen = True; continue
                    if re.fullmatch(r'\(표\)|\(상자\)', t): continue
                    (tail if seen else pre).append(x)
                for ln in pre: body.append(mkP(ln, PS_NORM))
                body.append(wrapP(data_table(parse_pipe(K))))
                for ln in tail: body.append(mkP(ln, PS_NORM))
            else:
                body.append(mkP(f'〔그림 프롬프트 시작 · {no}번〕', PS_NORM, CS_NUM))
                for ln in kl: body.append(mkP(ln, PS_NORM))
                body.append(mkP(f'〔그림 프롬프트 끝 · {no}번〕', PS_NORM, CS_NUM))
        if L and L != '없음.':
            pre = None if head_done else f'{no}.'
            body.append(mkP((' ' if pre else '') + f'{L} [{pt}점]', PS_ITEM if pre else PS_NORM, prefix=pre))
        if M and M != '없음.':
            bi = split_bogi(M)
            body.append(wrapP(bogi_table(bi, 3 if len(bi) > 3 else 1)))
        if N and N != '없음.':
            kind = detect_kind(N)
            hdr, rows = split_answers(N, kind)
            kind = pick_kind(kind, rows)
            body.append(wrapP(answer_table(kind, rows, hdr, ans=g(8))))
        body.append(mkP(''))
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
    for cell in sec.iter('CELL'):
        for pl in cell.findall('PARALIST'):
            if pl.get('VertAlign') != 'Top': pl.set('VertAlign', 'Top'); n += 1
    print(f"  셀 세로정렬 '위'로 변경: {n}칸")
    # HWP equation SCRIPT may use ASCII `~` as a Hancom spacing marker.
    # Normalize only visible CHAR content, preserving those generated markers.
    normalize_hml_char_tildes(sec)
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="no" ?>'
           '<HWPML Style="embed" SubVersion="10.0.0.0" Version="2.91">' + HEAD +
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
