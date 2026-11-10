import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

from app import kice, variants


def paper(questions=20):
    """2단 시험지 흉내: 쪽마다 왼쪽·오른쪽 단에 문항 10개씩."""
    import pymupdf
    doc = pymupdf.open()
    for first in range(1, questions + 1, 20):
        page = doc.new_page(width=600, height=842)
        for i in range(20):
            no = first + i
            if no > questions:
                break
            x = 30 if i < 10 else 320
            y = 90 + (i % 10) * 70
            page.insert_text((x, y), f'{no}. Question {no} text. Which is correct? [3점]' if no == 4 else f'{no}. Question {no} text?', fontsize=8, fontname='korea')
    data = doc.tobytes()
    doc.close()
    return data


def zipped(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)
    return out.getvalue()


ROW = ("<tr onMouseOver=\"x\"><td>1</td><td>{year}</td><td>{area}</td><td>{title}</td><td>-</td>"
       "<td><a href=\"javascript:fn_fileDown('{seq}');\" title='{name}'>a</a>"
       "<a href=\"javascript:fn_fileDown('9{seq}');\" title='정답표.zip'>b</a></td><td>-</td></tr>")


class FakeSite:
    def __init__(self):
        self.urls = []
        self.files = {
            '11': zipped({'01_물리학Ⅰ_문제.pdf': paper(), '02_화학Ⅰ_문제.pdf': paper(), '01_물리학Ⅰ_정답.pdf': b'%PDF-'}),
            '12': zipped({'05_물리학Ⅱ_문제.pdf': paper(8)}),          # 너무 적게 나뉜 시험지는 실패로 남는다
            '15': zipped({'물리I.pdf': paper()}),                     # 옛 수능: 파일 이름에 '문제'가 없다
        }

    def __call__(self, url):
        self.urls.append(url)
        if 'list.do' in url:
            if 'page=1' not in url:
                return b''
            if '1500234' in url:   # 수능 게시판
                body = ROW.format(year=2025, area='과학탐구', title='문제 및 정답', seq='11', name='과학탐구영역_문제지.zip') \
                     + ROW.format(year=2025, area='국어', title='문제 및 정답', seq='13', name='국어_문제지.pdf') \
                     + ROW.format(year=2020, area='과학탐구', title='문제 및 정답', seq='15', name='과학탐구.zip') \
                     + ROW.format(year=2016, area='과학탐구', title='문제 및 정답', seq='14', name='과학탐구_문제지.zip')
            else:                   # 모의평가 게시판: area 가 6월·9월, 영역은 title
                body = ROW.format(year=2025, area='6월', title='과학탐구', seq='12', name='과학탐구_문제지.zip')
            return body.encode()
        return self.files[url.rsplit('=', 1)[1]]


class KiceTests(unittest.TestCase):
    def setUp(self):
        self.wait = kice.WAIT
        kice.WAIT = 0

    def tearDown(self):
        kice.WAIT = self.wait

    def test_list_keeps_only_science_papers_in_range(self):
        exams = kice.list_exams(2026, FakeSite())
        self.assertEqual(exams, [(2025, '수능', '11'), (2025, '6월', '12'), (2020, '수능', '15')])

    def test_subject_names_are_normalized(self):
        self.assertEqual(kice.subject_of('01_물리I_문제.pdf'), '물리학Ⅰ')
        self.assertEqual(kice.subject_of('문제지_물리II.pdf'), '물리학Ⅱ')
        self.assertEqual(kice.subject_of('04_지구과학Ⅰ_문제.pdf'), '지구과학Ⅰ')
        self.assertEqual(kice.subject_of('국어_문제.pdf'), '')

    def test_build_makes_a_pack_the_variant_picker_can_read(self):
        site = FakeSite()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'kice-pack'
            rows = kice.build(out, site, 2026)
            self.assertEqual(len(rows), 60)
            index = json.loads((out / 'index.json').read_text(encoding='utf-8'))
            self.assertEqual({r['subject'] for r in index['questions']}, {'물리학Ⅰ', '화학Ⅰ'})
            first = next(r for r in index['questions'] if r['key'] == '2025-수능-물리학Ⅰ-04')
            self.assertEqual(first['label'], '2025학년도 대학수학능력시험 물리학Ⅰ 4번')
            self.assertEqual(first['points'], 3)
            self.assertTrue((out / 'q' / '2025-수능-물리학Ⅰ-04.webp').is_file())
            self.assertIn('Question 4', (out / 'text' / '2025-수능-물리학Ⅰ-04.txt').read_text(encoding='utf-8'))
            self.assertEqual(json.loads((out / 'done.json').read_text(encoding='utf-8')), ['2020-수능', '2025-수능'])
            self.assertTrue(any('2025-6월' in f for f in kice.status()['failed']))
            # 문제지 PDF는 남기지 않는다
            self.assertFalse(list(out.rglob('*.pdf')))
            # 같은 형식이라 기출 변형의 목록·그림이 그대로 읽는다
            original = variants.pack_dir
            variants.pack_dir = lambda: out
            try:
                self.assertTrue(variants.pack_index('물리학Ⅰ')['available'])
                self.assertEqual(len(variants.pack_index('물리학Ⅰ')['questions']), 40)
                self.assertTrue(variants.pack_image('2025-수능-물리학Ⅰ-04'))
            finally:
                variants.pack_dir = original
            # 다시 받으면 끝낸 시험은 건너뛴다
            site.urls.clear()
            kice.build(out, site, 2026)
            self.assertFalse(any('fileSeq=11' in u for u in site.urls))

    def test_question_start_glued_to_previous_choices_is_found(self):
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=842)
        # 선택지와 다음 문항 첫 줄이 한 글 덩어리로 들어간 시험지(2026 수능 생명과학Ⅰ 꼴): 단마다 덩어리 하나
        for x, numbers in ((30, range(1, 11)), (320, range(11, 21))):
            page.insert_text((x, 90), '\n'.join(f'{no}. Question {no}?\n① a ② b' for no in numbers), fontsize=8, fontname='korea')
        self.assertLess(len(page.get_text('blocks')), 20)
        self.assertEqual([q['no'] for q in kice.split_questions(doc)], list(range(1, 21)))
        doc.close()

    def test_header_page_number_and_tail_box_stay_out_of_questions(self):
        import pymupdf
        doc = pymupdf.open()
        for page_no in range(2):
            page = doc.new_page(width=600, height=842)
            page.insert_text((250, 60), '과학탐구 영역', fontsize=12, fontname='korea')
            page.insert_text((40, 60), str(page_no + 1), fontsize=12, fontname='korea')        # 머리말 띠의 쪽 번호
            for i in range(10):
                no = page_no * 10 + i + 1
                x, y = (30, 110 + i * 60) if i < 5 else (320, 110 + (i - 5) * 60)
                page.insert_text((x, y), f'{no}. Question {no}?\n① a ② b', fontsize=8, fontname='korea')
            page.draw_rect(pymupdf.Rect(285, 795, 315, 815))                                     # 쪽 번호 상자
            page.insert_text((292, 808), str(page_no + 1), fontsize=8, fontname='korea')
        last = doc[1]
        last.draw_rect(pymupdf.Rect(320, 420, 580, 470))                                          # '확인 사항' 상자
        last.insert_text((330, 435), '* 확인 사항', fontsize=8, fontname='korea')
        last.insert_text((330, 450), '○ 답안지의 해당란에 필요한 내용을 정확히 기입했는지 확인하시오.', fontsize=7, fontname='korea')
        questions = kice.split_questions(doc)
        self.assertEqual([q['no'] for q in questions], list(range(1, 21)))
        self.assertFalse(any('탐구' in q['text'] or '확인' in q['text'] for q in questions))
        spans = kice.spans_with_bottoms(doc, questions)
        self.assertLess(spans[-1][-1][3], 420)              # 마지막 문항은 '확인 사항' 상자 위에서 끝난다
        self.assertLess(spans[4][-1][3], 795)               # 단 끝 문항은 쪽 번호 상자 위에서 끝난다
        doc.close()

    def test_cancel_stops_before_next_exam(self):
        stop = threading.Event(); stop.set()
        with tempfile.TemporaryDirectory() as tmp:
            rows = kice.build(Path(tmp), FakeSite(), 2026, stop)
            self.assertEqual(rows, [])
            self.assertIn('멈췄습니다', kice.status()['stage'])


if __name__ == '__main__':
    unittest.main()
