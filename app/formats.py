"""교과별 세부 형식. 4종 유형은 그대로 두고 그 위에 평가원 꼴(지도 위치 대응형, 요약문 빈칸 등)을 고르게 한다.

목록은 question_formats.json 에 있다. instructions/기출-형식-매뉴얼/ 에서 뽑았다.
교사가 문항카드에서 고르면 AI 문항 작성 요청에 그 꼴의 설명이 들어간다.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'question_formats.json'


@lru_cache(maxsize=1)
def catalog():
    if not DATA.exists(): return []
    return json.loads(DATA.read_text(encoding='utf-8'))['formats']


def find(fid):
    return next((f for f in catalog() if f['id'] == fid), None)


def for_subject(subject_id):
    return [f for f in catalog() if subject_id in f['subjects']]


def normalize(value):
    """목록에서 빠진 형식이 남아 있어도 저장은 막지 않는다. 요청에 넣지 않을 뿐이다."""
    value = str(value or '').strip()
    if value and not re.fullmatch('[a-z0-9_]{1,64}', value): raise ValueError('세부 형식 ID 오류')
    return value


def prompt(card, subject_id=''):
    f = find(card.get('format') or '')
    if not f or (subject_id and subject_id not in f['subjects']): return ''
    lines = [f"세부 형식: {f['name']} ({f['manual']}). 문항 유형({card.get('type') or '미정'})은 그대로 두고 이 꼴로 쓴다.",
             f"- 자료: {f['material']}", f"- 발문: {f['question']}", f"- 선지: {f['choices']}", f"- 앱에서 만드는 법: {f['app']}"]
    if f.get('cautions'): lines.append(f"- 주의: {f['cautions']}")
    lines.append('기출 문항의 지문·선지를 옮기지 않고 꼴만 따른다. 교사 아이디어의 상황과 내용이 우선한다.')
    return '\n'.join(lines)
