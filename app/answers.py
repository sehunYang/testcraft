"""A clean, single-column answer booklet with native Hancom equations.

Reuse the school's font/style mappings and table-cell prototype. The question
paper template itself remains unchanged. HML is an internal conversion source.
"""
from __future__ import annotations

import copy
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .catalog import official_code
from .core import SUBJECTIVE_TYPES
from .mathtext import math_segments


def build_answer_hml(title: str, cards: list[dict], destination: Path) -> str:
    from tools import gen

    if not cards:
        raise ValueError('정답·해설을 만들 문항이 없습니다.')
    head = ET.fromstring(gen.HEAD)
    chars = head.find('.//CHARSHAPELIST')
    paras = head.find('.//PARASHAPELIST')

    def character(size, bold=False, color='0'):
        shape = copy.deepcopy(next(node for node in chars if node.get('Id') == gen.CS_BODY))
        identifier = str(max(int(node.get('Id')) for node in chars) + 1)
        shape.attrib.update(Id=identifier, Height=str(size), TextColor=color, BorderFillId='1')
        for node in list(shape):
            if node.tag in ('BOLD', 'ITALIC', 'UNDERLINE'): shape.remove(node)
        if bold: ET.SubElement(shape, 'BOLD')
        chars.append(shape); chars.set('Count', str(len(chars)))
        return identifier

    def paragraph(*, before=0, after=0, keep=False, page=False, align='Left', spacing=160):
        shape = copy.deepcopy(next(node for node in paras if node.get('Id') == '0'))
        identifier = str(max(int(node.get('Id')) for node in paras) + 1)
        shape.attrib.update(Id=identifier, Align=align, KeepWithNext=str(keep).lower(),
                            PageBreakBefore=str(page).lower(), WidowOrphan='true', KeepLines='false')
        shape.find('PARAMARGIN').attrib.update(Indent='0', Left='0', Right='0', Prev=str(before),
                                               Next=str(after), LineSpacing=str(spacing))
        shape.find('PARABORDER').set('BorderFill', '1')
        paras.append(shape); paras.set('Count', str(len(paras)))
        return identifier

    cs = {'title': character(2200, True), 'subtitle': character(1200), 'body': character(1100),
          'bold': character(1100, True), 'heading': character(1400, True),
          'meta': character(950, color='6710886'), 'table': character(950), 'table_head': character(950, True)}
    ps = {'title': paragraph(after=800, keep=True, spacing=125),
          'subtitle': paragraph(after=400, keep=True), 'meta': paragraph(after=600, keep=True),
          'heading': paragraph(before=1200, after=700, keep=True),
          'first_heading': paragraph(before=1200, after=700, keep=True, page=len(cards)>8),
          'body': paragraph(after=380), 'cell': paragraph(spacing=140, align='Center'),
          'cell_left': paragraph(spacing=140), 'summary_note': paragraph(before=500, after=0), 'spacer': paragraph(after=200)}
    secdef = copy.deepcopy(gen.SECDEF)
    # 시험지는 B4 2단이지만 정답과 해설은 교사가 보는 A4 문서다.
    secdef.find('PAGEDEF').attrib.update(Width='59528', Height='84188')
    secdef.find('PAGEDEF/PAGEMARGIN').attrib.update(Left='8504', Right='8504', Top='5668', Bottom='4252', Header='4252', Footer='4252', Gutter='0')
    section = ET.Element('SECTION', {'Id': '0'})
    first = gen.mkP('', ps['spacer'], cs['body'])
    first.find('TEXT').insert(0, secdef)
    section.append(first)

    def append(text, style='body', font=None):
        p = gen.mkP(str(text), ps[style], cs.get(font or style, cs['body']))
        section.append(p)
        return p

    append('정답과 해설', 'title')
    append(title, 'subtitle')
    total = sum(float(card.get('points') or 0) for card in cards)
    append(f'TestCraft  ·  {len(cards)}문항  ·  합계 {total:g}점', 'meta')
    append('정답 한눈에 보기', 'heading')
    rows = [['문항', '정답', '배점', '난이도', '성취기준']]
    written = {card['no']: order for order, card in enumerate((c for c in cards if c.get('type') in SUBJECTIVE_TYPES), 1)}
    label = lambda card: f"서답형 {written[card['no']]}" if card['no'] in written else f"{card['no']}번"
    rows.extend([[label(card), card['type'] if card['no'] in written else '①②③④⑤'[int(card['answer'])-1], f"{card['points']}점",
                  str(card.get('difficulty') or ''), official_code(str(card.get('standard') or ''))] for card in cards])
    table = gen.data_table(rows)
    page = secdef.find('PAGEDEF'); margin = page.find('PAGEMARGIN')
    body_width = int(page.get('Width')) - int(margin.get('Left')) - int(margin.get('Right'))
    widths = [4000, 4000, 6000, 6000, body_width-1230-20000]
    table.find('SHAPEOBJECT/SIZE').set('Width', str(sum(widths)+1230))
    table.find('SHAPEOBJECT/SIZE').set('Height', str(len(rows)*1750+566))
    for ri, row in enumerate(table.findall('ROW')):
        for ci, cell in enumerate(row.findall('CELL')):
            cell.set('Width', str(widths[ci])); cell.set('Height', '1750')
            cell.set('Header', str(ri == 0).lower())
            cell.find('PARALIST').set('VertAlign', 'Center')
            p = cell.find('PARALIST/P'); p.set('ParaShape', ps['cell_left'] if ci == 4 and ri else ps['cell'])
            for text in p.findall('TEXT'): text.set('CharShape', cs['table_head'] if ri == 0 else cs['table'])
    section.append(gen.wrapP(table, ps['body']))
    distribution = '  ·  '.join(f"{official_code(standard)} {sum(card.get('standard', '') == standard for card in cards)}문항"
                                for standard in sorted({card.get('standard', '') for card in cards}))
    append('성취기준 분포: ' + distribution, 'summary_note', 'meta')

    def explanation(value):
        lines = [[]]
        for kind, content in math_segments(str(value or '')):
            if kind == 'math': lines[-1].append((kind, content)); continue
            parts = content.replace('\r\n', '\n').split('\n')
            for index, part in enumerate(parts):
                if index: lines.append([])
                lines[-1].append(('text', part))
        for tokens in lines:
            p = ET.Element('P', {'ParaShape': ps['body'], 'Style': '0'})
            for index, (kind, content) in enumerate(tokens):
                if kind == 'math':
                    text = ET.SubElement(p, 'TEXT', {'CharShape': cs['body']})
                    text.append(gen.E_eq(gen.eqscript(content)))
                else:
                    if index == 0:
                        content = re.sub(r'^\s*#{1,6}\s+', '', content)
                        content = re.sub(r'^\s*[-*+]\s+', '• ', content)
                    for part in re.split(r'(\*\*[^*]+\*\*)', content):
                        if not part: continue
                        bold = part.startswith('**') and part.endswith('**')
                        text = ET.SubElement(p, 'TEXT', {'CharShape': cs['bold'] if bold else cs['body']})
                        ET.SubElement(text, 'CHAR').text = part[2:-2] if bold else part
            if not list(p): p = gen.mkP('', ps['spacer'], cs['body'])
            section.append(p)

    for index, card in enumerate(cards):
        if card['no'] in written:
            partial = '  ·  부분 점수 있음' if card.get('partial_credit') else ''
            append(f"{label(card)}  ·  {card['type']}  ·  {card['points']}점{partial}", 'first_heading' if index == 0 else 'heading', 'heading')
        else:
            answer = '①②③④⑤'[int(card['answer'])-1]
            append(f"{card['no']}번  ·  정답 {answer}  ·  {card['points']}점", 'first_heading' if index == 0 else 'heading', 'heading')
        metadata = f"{official_code(card.get('standard', ''))} {card.get('standard_name', '')}".strip()
        if card.get('concepts'): metadata += f"  |  {card['concepts']}"
        if metadata: append(metadata, 'meta')
        if card['no'] in written:
            append('모범 답안', 'body', 'bold'); explanation(card.get('model_answer') or '')
            append('채점 기준', 'body', 'bold'); explanation(card.get('rubric') or '')
            append('해설', 'body', 'bold')
        explanation(card.get('explanation') or '해설이 입력되지 않았습니다.')
    gen.normalize_hml_char_tildes(section)
    # Retain the native shape mappings and explicit widths rather than drawing a table as an image.
    for table in section.iter('TABLE'):
        actual = table.findall('ROW')
        if len(actual) != int(table.get('RowCount')) or any(len(row.findall('CELL')) != int(table.get('ColCount')) for row in actual):
            raise ValueError('정답·해설 요약표의 구조가 올바르지 않습니다.')
    root = ET.Element('HWPML', {'Style': 'embed', 'SubVersion': '10.0.0.0', 'Version': '2.91'})
    root.append(head); ET.SubElement(root, 'BODY').append(section); ET.SubElement(root, 'TAIL')
    xml = '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>' + ET.tostring(root, encoding='unicode')
    Path(destination).write_text(xml, encoding='utf-8')
    return xml
