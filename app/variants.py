"""기출 변형: 원본 문항(기출 팩 또는 교사가 올린 이미지·PDF)을 고르고, 고른 변형 방식만 AI에게 전한다.

원본 그림은 시험 폴더의 sources/ 에만 둔다. 학생용 시험지에는 원본 문장·그림이 들어가지 않고, 출처는 해설지에만 적는다.
"""
import base64
import io
import json
import re
from pathlib import Path

from . import runtime

ROOT = Path(__file__).resolve().parents[1]
METHODS = {
    'numbers': ('수치·조건만 바꾸기', '같은 상황과 구조를 두고 주어진 수치·조건과 그에 따른 정답만 바꾼다. 묻는 개념과 풀이 단계 수는 원본과 같다.'),
    'situation': ('상황 바꾸고 원리 유지', '묻는 개념·원리와 풀이 구조는 원본과 같게 두고, 물리적 상황·소재·자료의 꼴을 새로 정한다.'),
    'form': ('유형·난이도 바꾸기', '교사가 정한 목표 유형과 난이도에 맞게 발문·선택지 구조와 사고 단계를 바꾼다.'),
}
SOURCE_NAME = re.compile(r'[a-f0-9]{16}\.png')
MAX_UPLOAD = 25 * 1024 * 1024


def pack_dir():
    """기출 팩 위치: 앱과 함께 깐 팩 → 사용자 데이터 폴더 → 개발용 .runtime."""
    for folder in (ROOT / 'kice-pack', runtime.user_root(ROOT) / 'kice-pack', ROOT / '.runtime/kice-pack'):
        if (folder / 'index.json').is_file():
            return folder
    return None


def pack_index(subject=''):
    folder = pack_dir()
    if not folder:
        return {'available': False, 'subjects': [], 'questions': []}
    data = json.loads((folder / 'index.json').read_text(encoding='utf-8'))
    rows = [r for r in data['questions'] if not subject or r['subject'] == subject]
    return {'available': True, 'subjects': data['subjects'], 'questions': rows}


def _pack_row(key):
    folder = pack_dir()
    if not folder or not re.fullmatch(r'\d{4}-[0-9가-힣]+-[가-힣ⅠⅡ]+-\d{2}', key or ''):
        raise ValueError('기출 문항을 찾을 수 없습니다.')
    data = json.loads((folder / 'index.json').read_text(encoding='utf-8'))
    row = next((r for r in data['questions'] if r['key'] == key), None)
    if not row:
        raise ValueError('기출 문항을 찾을 수 없습니다.')
    return folder, row


def pack_image(key):
    folder, row = _pack_row(key)
    return (folder / 'q' / f"{row['key']}.webp").read_bytes()


def _png(img):
    out = io.BytesIO()
    img.save(out, 'PNG', optimize=True)
    return out.getvalue()


def _image_from_upload(name, data, page, box=None):
    from PIL import Image
    if len(data) > MAX_UPLOAD:
        raise ValueError('원본 파일은 25MB 이하로 올려 주세요.')
    if name.lower().endswith('.pdf') or data[:5] == b'%PDF-':
        import pymupdf
        doc = pymupdf.open(stream=data, filetype='pdf')
        if not 1 <= page <= len(doc):
            raise ValueError(f'PDF 쪽 번호는 1~{len(doc)} 사이로 적어 주세요.')
        pix = doc[page - 1].get_pixmap(matrix=pymupdf.Matrix(2, 2), colorspace=pymupdf.csGRAY)
        sheet = doc[page - 1]
        r = sheet.rect                                         # 자른 영역의 글만 겹침 검사 기준으로 쓴다
        text = sheet.get_text(clip=pymupdf.Rect(r.x0 + box[0] * r.width, r.y0 + box[1] * r.height, r.x0 + box[2] * r.width, r.y0 + box[3] * r.height)) if box else sheet.get_text()
        doc.close()
        return Image.open(io.BytesIO(pix.tobytes('png'))).convert('L'), text
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise ValueError('PNG·JPG 그림이나 PDF만 올릴 수 있습니다.') from None
    return img.convert('RGB'), ''


def save_source(folder, payload, new_id):
    """원본을 시험 폴더 sources/ 에 PNG로 저장하고 카드에 넣을 source 정보를 돌려준다."""
    from PIL import Image
    kind = payload.get('kind')
    folder = Path(folder) / 'sources'
    folder.mkdir(parents=True, exist_ok=True)
    name = f'{new_id}.png'
    if kind == 'kice':
        pack, row = _pack_row(str(payload.get('key', '')))
        img = Image.open(pack / 'q' / f"{row['key']}.webp")
        text_file = pack / 'text' / f"{row['key']}.txt"
        text = text_file.read_text(encoding='utf-8') if text_file.is_file() else ''
        source = {'kind': 'kice', 'key': row['key'], 'label': row['label'], 'subject': row['subject'], 'form': row.get('form', '')}
    elif kind == 'upload':
        raw = base64.b64decode(str(payload.get('data', '')).split(',')[-1] or b'', validate=False)
        crop = payload.get('crop')
        box = None
        if crop:                                               # 0~1 비율 상자 [x0, y0, x1, y1]
            x0, y0, x1, y1 = box = tuple(max(0.0, min(1.0, float(v))) for v in crop)
            if x1 - x0 < .03 or y1 - y0 < .03:
                raise ValueError('자를 영역이 너무 작습니다.')
        img, text = _image_from_upload(str(payload.get('name', '')), raw, int(payload.get('page') or 1), box)
        if box:
            img = img.crop((round(x0 * img.width), round(y0 * img.height), round(x1 * img.width), round(y1 * img.height)))
        label = str(payload.get('label', '')).strip()[:120] or '교사가 올린 원본'
        source = {'kind': 'upload', 'key': '', 'label': label, 'subject': '', 'form': ''}
    else:
        raise ValueError('원본 종류는 kice 또는 upload 이어야 합니다.')
    if max(img.size) > 2400:
        img.thumbnail((2400, 2400))
    (folder / name).write_bytes(_png(img))
    if text:
        (folder / f'{new_id}.txt').write_text(re.sub(r'\s+', ' ', text).strip(), encoding='utf-8')
    source['image'] = name
    return source


def source_file(folder, source, suffix='.png'):
    name = (source or {}).get('image', '')
    if not SOURCE_NAME.fullmatch(name or ''):
        return None
    path = Path(folder) / 'sources' / name.replace('.png', suffix)
    return path if path.is_file() else None


def normalize(card):
    """카드의 variant 칸을 정리한다. 작성 중일 수 있으므로 비어 있는 것은 허용하고, 생성할 때 check()로 막는다."""
    value = card.get('variant')
    if card.get('authoring_mode') != 'variant' and not value:
        card['variant'] = None
        return
    value = value if isinstance(value, dict) else {}
    methods = [m for m in METHODS if m in (value.get('methods') or [])]
    source = value.get('source') if isinstance(value.get('source'), dict) else None
    if source:
        source = {k: str(source.get(k, ''))[:200] for k in ('kind', 'key', 'label', 'subject', 'form', 'image')}
        if source['kind'] not in ('kice', 'upload') or not SOURCE_NAME.fullmatch(source['image']):
            source = None
    card['variant'] = {
        'methods': methods,
        'memo': str(value.get('memo', ''))[:2000],
        'source': source,
        'changes': [str(c)[:300] for c in (value.get('changes') or [])][:12],
        'overlap': float(value.get('overlap') or 0),
    }


def check(card):
    v = card.get('variant') or {}
    if not (v.get('source') or {}).get('image'):
        raise ValueError(f"{card.get('no', '')}번: 변형할 원본 기출을 먼저 골라 주세요.")
    if not v.get('methods'):
        raise ValueError(f"{card.get('no', '')}번: 변형 방식을 하나 이상 골라 주세요.")


def prompt(card):
    """질문 프롬프트에 덧붙일 변형 지시. 고른 방식만 넣고, 고르지 않은 쪽은 원본대로 두게 한다."""
    v = card.get('variant') or {}
    chosen = [m for m in METHODS if m in v.get('methods', [])]
    lines = ['이 문항은 첨부한 원본 기출 문항 그림을 바탕으로 한 변형 문항이다. 원본을 읽고 다음 변형 방식만 적용한다.']
    lines += [f'- {METHODS[m][0]}: {METHODS[m][1]}' for m in chosen]
    if 'form' in chosen:
        lines.append(f"- 목표 유형은 '{card.get('type') or '원본과 같은 유형'}', 목표 난이도는 '{card.get('difficulty') or '원본과 비슷하게'}'이다.")
    else:
        lines.append('- 유형·난이도는 바꾸지 않는다. 원본과 같은 유형으로 쓰고 난이도도 원본 수준으로 둔다. 카드의 type이 비어 있으면 원본 유형을 넣는다.')
    if 'situation' not in chosen:
        lines.append('- 상황·소재는 원본과 같은 종류로 둔다.')
    lines += [
        '- 원본의 문장·자료·선택지를 그대로 옮기지 않는다. 같은 뜻이라도 새 문장으로 쓰고, 수치·기호·순서를 원본과 같게 두지 않는다.',
        '- 원본 그림을 복사하지 않는다. 필요한 그림은 현재 그림 규칙(도식 명세 등)으로 새로 계획한다.',
        '- 성취기준 칸이 비어 있으면 원본이 다루는 내용에 맞는 성취기준을 추정해 standard 관련 내용을 review_note에 제안한다.',
        '- variant_changes에는 원본과 달라진 점을 교사가 확인할 수 있게 짧은 문장 목록으로 적는다(예: "질량 2 kg → 3 kg", "빗면 → 원형 궤도").',
    ]
    if v.get('memo'):
        lines.append(f"- 교사 메모: {v['memo']}")
    return '\n'.join(lines)


def _grams(text, n=6):
    text = re.sub(r'[\s$\\{}]', '', text or '')
    return {text[i:i + n] for i in range(max(0, len(text) - n + 1))}


def overlap(source_text, card):
    """원본 글과 새 문항 글이 6글자 단위로 얼마나 겹치는지(0~1). 원본 글이 없으면 0."""
    a = _grams(source_text)
    if not a:
        return 0.0
    b = _grams(' '.join(str(card.get(k, '')) for k in ('stem', 'question', 'statements', 'choices', 'material')))
    return round(len(a & b) / max(1, min(len(a), len(b))), 3) if b else 0.0


def overlap_limit(card):
    """겹침 경고 기준. '수치·조건만 바꾸기'만 고르면 문장 틀을 원본대로 두므로 50%, 그 밖에는 25%."""
    return .5 if ((card.get('variant') or {}).get('methods') or []) == ['numbers'] else .25


def answer_note(card):
    """해설지에 붙일 출처 줄. 기출 팩이면 '○○학년도 … ○번 변형', 올린 원본이면 교사가 적은 이름."""
    source = ((card.get('variant') or {}).get('source') or {}) if card.get('authoring_mode') == 'variant' else {}
    return f"[출처] {source['label']} 변형" if source.get('label') else ''
