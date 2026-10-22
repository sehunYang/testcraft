"""Validation helpers for Hancom's HWPX package output."""
from pathlib import Path
from collections import Counter
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile


def _local_name(tag):
    return tag.rsplit('}', 1)[-1].lower()


def _text_signature(text):
    normalized = unicodedata.normalize('NFKC', text or '')
    return ''.join(re.findall(r'[A-Za-z0-9가-힣]', normalized))


def validate_hwpx_package(path, source_hml=None):
    """Raise ValueError unless *path* is a readable HWPX package.

    When the source HML is supplied, also check that native equations and
    pictures were retained. HWPX section XML is parsed so a ZIP with only
    correctly named but corrupt XML parts is rejected.
    """
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f'HWPX 파일이 없거나 비어 있습니다: {path.name}')
    try:
        with zipfile.ZipFile(path) as package:
            bad = package.testzip()
            if bad:
                raise ValueError(f'HWPX 압축 항목이 손상되었습니다: {bad}')
            infos = package.infolist()
            if not infos or infos[0].filename != 'mimetype' or infos[0].compress_type != zipfile.ZIP_STORED:
                raise ValueError('HWPX mimetype 항목의 순서나 압축 방식이 올바르지 않습니다.')
            names = set(package.namelist())
            required = {'mimetype', 'Contents/content.hpf'}
            missing = required - names
            sections = sorted(name for name in names
                              if re.fullmatch(r'Contents/section\d+\.xml', name))
            if missing or not sections:
                detail = ', '.join(sorted(missing)) if missing else 'Contents/section*.xml'
                raise ValueError(f'HWPX 필수 구성요소가 없습니다: {detail}')
            mime = package.read('mimetype').decode('ascii', errors='replace').strip()
            if mime != 'application/hwp+zip':
                raise ValueError('HWPX mimetype 값이 올바르지 않습니다.')
            ET.fromstring(package.read('Contents/content.hpf'))
            section_roots = [ET.fromstring(package.read(name)) for name in sections]
            section_nodes = [node for root in section_roots for node in root.iter()]
            visible_text = ''.join(node.text or '' for node in section_nodes
                                   if _local_name(node.tag) in ('t', 'char'))
            if not visible_text.strip():
                raise ValueError('HWPX 본문에 읽을 수 있는 문자가 없습니다.')
            if source_hml is not None:
                source_root = ET.parse(source_hml).getroot()
                source_nodes = list(source_root.iter())
                source_equations = sum(_local_name(node.tag) == 'equation' for node in source_nodes)
                source_pictures = sum(_local_name(node.tag) in ('picture', 'pic') for node in source_nodes)
                source_text = _text_signature(''.join(node.text or '' for node in source_nodes
                                                       if _local_name(node.tag) == 'char'))
                output_text = _text_signature(visible_text)
                if len(source_text) >= 24:
                    source_chars, output_chars = Counter(source_text), Counter(output_text)
                    retained = sum(min(count, output_chars.get(char, 0))
                                   for char, count in source_chars.items())
                    if retained / len(source_text) < 0.75:
                        raise ValueError('HWPX 본문 글자가 원본 HML보다 크게 줄었습니다.')
                output_equations = sum(_local_name(node.tag) == 'equation' for node in section_nodes)
                output_pictures = sum(_local_name(node.tag) in ('picture', 'pic') for node in section_nodes)
                if output_equations < source_equations:
                    raise ValueError(f'HWPX 수식이 보존되지 않았습니다 ({output_equations}/{source_equations}).')
                if output_pictures < source_pictures:
                    raise ValueError(f'HWPX 그림이 보존되지 않았습니다 ({output_pictures}/{source_pictures}).')
    except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError, UnicodeError) as exc:
        raise ValueError(f'HWPX 패키지를 읽을 수 없습니다: {exc}') from exc
    return {'valid': True, 'sections': len(sections), 'text_chars': len(visible_text.strip()),
            'equations': output_equations if source_hml is not None else None,
            'pictures': output_pictures if source_hml is not None else None}
