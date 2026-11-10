# -*- coding: utf-8 -*-
"""평가원 공식 게시판에서 과학탐구 문제지를 이 PC로 받아 '기출 묶음'(문항별 그림·글)을 만든다.

묶음은 설치 파일로 나눠 주지 않는다. 교사가 앱에서 직접 받기를 누르면 이 PC가 평가원 홈페이지에서
문제지를 받고, 문항별로 잘라 사용자 데이터 폴더의 kice-pack/ 에 둔다. 원본 PDF는 자른 뒤 지운다.
"""
import html
import io
import json
import re
import threading
import time
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

from . import runtime

SITE = 'https://www.suneung.re.kr'
BOARDS = {'수능': '1500234', '모의평가': '1500236'}
FIRST = 2018                      # 최근 10개 학년도 안팎
WAIT = 0.5                        # 공공 사이트에 부담을 주지 않도록 요청 사이에 쉰다
SCIENCE = ('물리학Ⅰ', '물리학Ⅱ', '화학Ⅰ', '화학Ⅱ', '생명과학Ⅰ', '생명과학Ⅱ', '지구과학Ⅰ', '지구과학Ⅱ')
ROUNDS = ('수능', '9월', '6월')
ZOOM = 2.0                        # 144 dpi: 그림 속 작은 글씨까지 읽힌다
FOOTER = 72                       # 쪽 아래 쪽 번호 상자 높이(pt)
HEADER = 70                       # 쪽 위 과목명 띠(pt)
HEAD_SIZE = 18                    # 머리말 글자 크기 하한(pt)
HEAD = re.compile(r'탐구영역')                      # 쪽 위 과목 띠
FIRST_HEAD = re.compile(r'탐구영역|수험번호|^성명$|^제\d교시$')   # 첫 쪽은 성명·수험 번호 칸까지 머리말이다
TAIL = re.compile(r'확인\s*사항|답안지의\s*해당란')
START = re.compile(r'^\s*(\d{1,2})\s*\.(\s|$)')
POINTS = re.compile(r'\[\s*(\d)\s*점\s*\]')
FORMS = [('합답형', re.compile(r'(보기|보 기).{0,14}(있는 대로|고른 것)|있는 대로 고른', re.S)),
         ('값 구하기', re.compile(r'(값|합|비|시간|거리|질량|속력|농도|크기)[은는]\?|구하시오')),
         ('부정 판단', re.compile(r'(않은|아닌|없는|틀린) 것[은을]')),
         ('긍정 판단', re.compile(r'(적절한|옳은|알맞은|맞는|해당하는|설명한) 것[은을]|것[은을]\?|것을 고르시오'))]
NOTICE = ('평가원 공식 홈페이지(suneung.re.kr)에서 수능·6월·9월 모의평가 과학탐구 문제지를 이 PC로 받습니다. '
          '문제의 저작권은 한국교육과정평가원에 있습니다. 학교 시험 출제를 위한 변형 원본으로만 쓰고, 다시 배포하지 마세요.')


ROOT = Path(__file__).resolve().parents[1]


def pack_dir():
    return runtime.user_root(ROOT) / 'kice-pack'


# ---------- 평가원 게시판 ----------

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (TestCraft)'})
    with urllib.request.urlopen(req, timeout=120) as res:
        return res.read()


def board_rows(page):
    """게시판 한 쪽의 행을 (학년도, 영역, 제목, 파일들)로 읽는다."""
    for tr in re.findall(r'<tr onMouseOver.*?</tr>', page, re.S):
        cells = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
        if len(cells) < 7:
            continue
        files = re.findall(r"fn_fileDown\('(\w+)'\);\" title='([^']*)'", tr)
        yield {'year': int(re.sub(r'\D', '', cells[1]) or 0), 'area': html.unescape(cells[2]).strip(),
               'title': html.unescape(re.sub(r'<[^>]+>', '', cells[3])).strip(),
               'files': [{'seq': seq, 'name': html.unescape(name)} for seq, name in files]}


def exam_of(kind, row):
    """게시판 행을 (학년도, 시험, 문제지 파일 seq)로. 과학탐구 문제지가 아니면 None.
    수능 게시판은 영역이 area, 모의평가 게시판은 area 가 6월·9월이고 영역은 title 에 있다."""
    round_name, area = ('수능', row['area']) if kind == '수능' else (row['area'], row['title'])
    if '과학' not in area or round_name not in ROUNDS:
        return None
    papers = [f for f in row['files'] if not re.search(r'정답|대본|듣기|음원', f['name'])]
    papers.sort(key=lambda f: '문제' not in f['name'])   # 옛 수능은 '과학탐구영역.zip'처럼 '문제'가 이름에 없다
    return (row['year'], round_name, papers[0]['seq']) if papers else None


def list_exams(last=None, get=fetch):
    """받을 시험 목록 [(학년도, 시험, seq)]. 게시판은 최신순이라 FIRST 보다 옛 학년도가 나오면 멈춘다."""
    last = last or date.today().year + 1
    found = []
    for kind, board in BOARDS.items():
        for page_no in range(1, 40):
            items = list(board_rows(get(f'{SITE}/boardCnts/list.do?boardID={board}&m=0403&s=suneung&page={page_no}').decode('utf-8', 'replace')))
            if not items:
                break
            found += [e for e in (exam_of(kind, r) for r in items if FIRST <= r['year'] <= last) if e]
            if items[-1]['year'] < FIRST:
                break
            time.sleep(WAIT)
    return sorted(set(found), key=lambda e: (-e[0], ROUNDS.index(e[1])))


def pdfs_in(data):
    """받은 파일(zip 또는 PDF)에서 (이름, PDF 바이트)를 꺼낸다. 압축 안의 경로는 믿지 않고 이름만 쓴다."""
    if data[:5] == b'%PDF-':
        yield '', data
        return
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            raw = info.filename
            try:
                raw = raw.encode('cp437').decode('cp949', 'replace')    # 한글 이름이 cp949로 들어 있는 압축이 많다
            except UnicodeEncodeError:
                pass
            name = raw.replace('\\', '/').rsplit('/', 1)[-1]
            if info.is_dir() or not name.lower().endswith('.pdf') or re.search(r'정답|대본|짝수', name):
                continue
            body = z.read(info)
            if body[:5] == b'%PDF-':
                yield name, body


def subject_of(name):
    name = re.sub(r'[\s_·()]', '', name).replace('II', 'Ⅱ').replace('ⅠⅠ', 'Ⅱ')
    name = re.sub(r'(?<=[가-힣])I', 'Ⅰ', name)
    for old, new in (('물리Ⅰ', '물리학Ⅰ'), ('물리Ⅱ', '물리학Ⅱ')):
        if old in name and new not in name:
            name = name.replace(old, new)
    return next((s for s in SCIENCE if s in name), '')


# ---------- 문항 자르기 ----------

def lines_of(page):
    """쪽의 글 줄을 왼쪽 단, 오른쪽 단 순서로 [(x0, y0, y1, 글, 글자 크기)]. 글 덩어리 단위로 읽으면
    앞 문항의 선택지 덩어리 끝에 다음 문항 번호가 붙어 나오는 시험지가 있어 줄 단위로 읽는다."""
    mid = page.rect.width / 2
    out = []
    for block in page.get_text('dict')['blocks']:
        if block.get('type') != 0:
            continue
        for line in block['lines']:
            text = ''.join(span['text'] for span in line['spans'])
            if text.strip():
                x0, y0, _, y1 = line['bbox']
                out.append((x0, y0, y1, text, max(span['size'] for span in line['spans'])))
    return sorted(out, key=lambda l: (l[0] >= mid, l[1]))


def box_top(boxes, x, y):
    """(x, y) 글자를 감싼 상자(쪽 번호 상자, '확인 사항' 상자)가 있으면 그 윗선, 없으면 글자 위."""
    return min([r.y0 for r in boxes if r.x0 - 2 <= x <= r.x1 and y - 30 <= r.y0 <= y + 2 and r.height < 200], default=y)


def page_foot(page, lines=None, boxes=None):
    """문항이 끝나는 쪽 아래 경계. 가운데 아래쪽의 쪽 번호(숫자만 있는 줄)와 그 상자 바로 위,
    쪽 번호가 없으면 쪽 아래 FOOTER 높이를 뺀 곳."""
    mid = page.rect.width / 2
    numbers = [(x0, y0) for x0, y0, _, text, _ in (lines or lines_of(page))
               if y0 > page.rect.height * .85 and abs(x0 - mid) < 60 and re.fullmatch(r'\s*\d{1,2}\s*', text)]
    if not numbers:
        return page.rect.height - FOOTER
    lowest = max(y for _, y in numbers)          # 분수의 숫자 같은 본문 숫자를 빼고, 맨 아래 쪽 번호 상자의 숫자만 남긴다
    numbers = [(x, y) for x, y in numbers if y >= lowest - 15]
    boxes = page_boxes(page) if boxes is None else boxes
    return min(box_top(boxes, x, y) for x, y in numbers) - 3


def page_boxes(page):
    """상자와 가로선(선 네 개로 그린 상자의 윗선 포함)의 영역."""
    return [d['rect'] for d in page.get_drawings() if d['rect'].width > 10]


def header_bottom(page, lines, pattern):
    """쪽 위 머리말 띠의 아래 끝. 위에서부터 내려가며 머리말 줄(20pt 안팎의 큰 글자, '과학탐구 영역',
    첫 쪽의 성명·수험 번호)을 모으고, 첫 본문 줄을 만나면 멈춘다. '과학탐 | 구 영역'처럼 두 단에
    갈라진 띠도 글자 크기로 찾고, 그림 속 큰 글자는 본문 아래에 있으므로 머리말로 치지 않는다."""
    bottom = 0
    for _, y0, y1, text, size in sorted(lines, key=lambda l: l[1]):
        if y0 > page.rect.height * .25:
            break
        if size >= HEAD_SIZE or pattern.search(re.sub(r'[\s`]', '', text)):
            bottom = max(bottom, y1)
        elif y0 > bottom:          # 머리말 아래의 첫 본문 줄
            break
    return bottom


def split_questions(doc):
    """문항 번호로 나눈다. 번호는 차례로 늘어나는 것만 믿는다. 본문 안의 '3. ' 같은 글에 속지 않기 위해서다."""
    found, current, expected = [], None, 1
    for page_no, page in enumerate(doc):
        mid = page.rect.width / 2
        lines = lines_of(page)
        # 쪽 위 과목 띠('과학탐구영역'과 같은 줄의 쪽 번호·과목명)와 쪽 아래 쪽 번호·저작권 줄은 문항이 아니다
        head = header_bottom(page, lines, FIRST_HEAD if page_no == 0 else HEAD)
        foot = page_foot(page, lines)
        for x0, y0, y1, text, _ in lines:
            if '저작권' in text or y1 <= head + 3 or y0 >= foot:
                continue
            if TAIL.search(text):       # 시험지 끝 '확인 사항' 상자부터는 문항이 아니다
                current = None
                continue
            match = START.match(text)
            if match and int(match.group(1)) == expected:
                current = {'no': expected, 'text': '', 'spans': []}
                found.append(current); expected += 1
            if current is None:
                continue
            current['text'] += text + '\n'
            side = x0 >= mid
            spans = current['spans']
            if spans and spans[-1][0] == page_no and spans[-1][1] == side:
                spans[-1][2] = min(spans[-1][2], y0); spans[-1][3] = max(spans[-1][3], y1)
            else:
                spans.append([page_no, side, y0, y1])
    return found


def spans_with_bottoms(doc, questions):
    """문항 범위의 아래 끝을 같은 단의 다음 문항 시작(없으면 단의 끝)까지 늘린다. 글 덩어리 사이 그림이 잘리지 않게."""
    starts = {}
    for q in questions:
        page_no, side, top, _ = q['spans'][0]
        starts.setdefault((page_no, side), []).append(top)
    tails = {}
    out = []
    for q in questions:
        spans = []
        for page_no, side, top, bottom in q['spans']:
            page = doc[page_no]
            later = [t for t in starts.get((page_no, side), []) if t > top + 1]
            mid = page.rect.width / 2
            # 시험지 끝의 '확인 사항' 상자와 저작권 줄은 문항이 아니다(쪽마다 한 번만 찾는다)
            if page_no not in tails:
                lines, boxes = lines_of(page), page_boxes(page)
                tails[page_no] = ([(x >= mid, y, box_top(boxes, x, y)) for x, y, _, text, _ in lines if TAIL.search(text)],
                                  page_foot(page, lines, boxes))
            marks, foot = tails[page_no]
            tail = [edge for s, y, edge in marks if s == side and y > top + 1]
            # 다음 문항 시작, '확인 사항' 상자 테두리, 쪽 번호 상자 가운데 가장 위에서 끊는다
            end = min([t - 4 for t in later] + [t - 3 for t in tail] + [foot])
            spans.append((page_no, side, max(HEADER - 20, top - 6), max(bottom + 4, end)))
        out.append(spans)
    return out


def render(doc, spans):
    import pymupdf
    from PIL import Image, ImageOps
    parts = []
    for page_no, side, top, bottom in spans:
        page = doc[page_no]; mid = page.rect.width / 2
        left, right = (mid, page.rect.width) if side else (0, mid)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), clip=pymupdf.Rect(left + 4, top, right - 4, bottom), colorspace=pymupdf.csGRAY)
        img = Image.open(io.BytesIO(pix.tobytes('png'))).convert('L')
        box = ImageOps.invert(img).getbbox()          # 흰 여백을 걷어 낸다
        if box:
            img = img.crop((max(0, box[0] - 12), max(0, box[1] - 12), min(img.width, box[2] + 12), min(img.height, box[3] + 12)))
        parts.append(img)
    sheet = Image.new('L', (max(p.width for p in parts), sum(p.height for p in parts) + 16 * (len(parts) - 1)), 255)
    y = 0
    for p in parts:
        sheet.paste(p, (0, y)); y += p.height + 16
    return sheet


def classify(text):
    head = re.sub(r'\s+', ' ', text)
    match = re.search(r'[^.?!]*(\?|시오\.)', head)
    ask = match.group(0).strip() if match else head[:120]
    return next((name for name, pattern in FORMS if pattern.search(ask)), '기타'), ask


def key_of(year, round_name, subject, no):
    return f'{year}-{round_name}-{subject}-{no:02d}'


def label_of(year, round_name, subject, no):
    exam = '대학수학능력시험' if round_name == '수능' else f'{round_name} 모의평가'
    return f'{year}학년도 {exam} {subject} {no}번'


def pack_paper(pdf, year, round_name, subject, out):
    """문제지 PDF 하나를 문항별 그림·글로 잘라 out 에 두고, 목록 행을 돌려준다. 15문항 미만이면 실패로 본다."""
    import pymupdf
    doc = pymupdf.open(stream=pdf, filetype='pdf')
    try:
        questions = split_questions(doc)
        if len(questions) < 15:
            raise ValueError(f'문항을 {len(questions)}개만 찾았습니다')
        rows = []
        for q, spans in zip(questions, spans_with_bottoms(doc, questions)):
            no = q['no']; key = key_of(year, round_name, subject, no)
            render(doc, spans).save(out / 'q' / f'{key}.webp', 'WEBP', quality=72, method=6)
            text = re.sub(r'\s+', ' ', q['text']).strip()
            (out / 'text' / f'{key}.txt').write_text(text, encoding='utf-8')
            form, ask = classify(text)
            points = POINTS.search(text)
            rows.append({'key': key, 'year': year, 'round': round_name, 'subject': subject, 'no': no,
                         'label': label_of(year, round_name, subject, no), 'form': form, 'graphic': '',
                         'points': int(points.group(1)) if points else 0, 'ask': ask[:120]})
        return rows
    finally:
        doc.close()


def write_index(out, rows):
    rows = sorted(rows, key=lambda r: (SCIENCE.index(r['subject']), -r['year'], ROUNDS.index(r['round']) if r['round'] in ROUNDS else 9, r['no']))
    tmp = out / 'index.json.tmp'
    tmp.write_text(json.dumps({'version': 1, 'subjects': list(SCIENCE), 'questions': rows}, ensure_ascii=False), encoding='utf-8')
    tmp.replace(out / 'index.json')


# ---------- 앱에서 받기 (한 번에 하나) ----------

_lock = threading.Lock()
_state = {'running': False, 'stage': '', 'done': 0, 'total': 0, 'questions': 0, 'failed': [], 'error': '', 'finished': False}
_cancel = threading.Event()


def status():
    with _lock:
        return {**_state, 'failed': list(_state['failed']), 'notice': NOTICE, 'years': [FIRST, date.today().year + 1]}


def _set(**values):
    with _lock:
        _state.update(values)


def build(out, get=fetch, last=None, cancel=None):
    """시험 목록을 읽고 한 시험씩 받아 자른다. 이미 만든 시험(done.json)은 건너뛰어 이어 받을 수 있다."""
    cancel = cancel or threading.Event()
    (out / 'q').mkdir(parents=True, exist_ok=True); (out / 'text').mkdir(exist_ok=True)
    done_file = out / 'done.json'
    done = set(json.loads(done_file.read_text(encoding='utf-8'))) if done_file.is_file() else set()
    index_file = out / 'index.json'
    rows = json.loads(index_file.read_text(encoding='utf-8'))['questions'] if index_file.is_file() else []
    _set(stage='평가원 게시판에서 시험 목록을 읽는 중입니다.')
    exams = list_exams(last, get)
    _set(total=len(exams), done=sum(f'{y}-{r}' in done for y, r, _ in exams), questions=len(rows))
    for year, round_name, seq in exams:
        tag = f'{year}-{round_name}'
        if tag in done:
            continue
        if cancel.is_set():
            _set(stage='받기를 멈췄습니다. 다시 누르면 이어서 받습니다.'); return rows
        _set(stage=f'{year}학년도 {round_name} 과학탐구 문제지를 받는 중입니다.')
        try:
            data = get(f'{SITE}/boardCnts/fileDown.do?fileSeq={seq}')
            new = []
            for name, pdf in pdfs_in(data):
                subject = subject_of(name)
                if not subject:
                    continue
                try:
                    new += pack_paper(pdf, year, round_name, subject, out)
                except Exception as e:
                    with _lock: _state['failed'].append(f'{tag} {subject}: {e}')
            if not new:
                raise ValueError('과학탐구 문제지를 찾지 못했습니다')
            keys = {r['key'] for r in new}
            rows = [r for r in rows if r['key'] not in keys] + new
            write_index(out, rows)
            done.add(tag); done_file.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding='utf-8')
        except Exception as e:
            with _lock: _state['failed'].append(f'{tag}: {e}')
        with _lock:
            _state['done'] += 1; _state['questions'] = len(rows)
        time.sleep(WAIT)
    _set(stage=f'기출 묶음을 만들었습니다. 과학탐구 {len(rows)}문항을 고를 수 있습니다.')
    return rows


def start(out=None):
    """백그라운드에서 받기를 시작한다. 이미 받는 중이면 상태만 돌려준다."""
    with _lock:
        busy = _state['running']
        if not busy:
            _state.update(running=True, finished=False, error='', failed=[], stage='시작하는 중입니다.', done=0, total=0)
    if busy:
        return status()
    _cancel.clear()
    target = Path(out) if out else pack_dir()

    def work():
        try:
            build(target, cancel=_cancel)
        except Exception as e:
            _set(error=f'평가원 홈페이지에서 받지 못했습니다: {e}', stage='')
        finally:
            _set(running=False, finished=True)
    threading.Thread(target=work, name='kice-pack', daemon=True).start()
    return status()


def cancel():
    _cancel.set()
    return status()
