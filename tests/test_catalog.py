import io
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
import openpyxl
from app import catalog, core
from test_support import cleanup_tempdir

class SubjectCatalogTests(unittest.TestCase):
    def test_every_subject_in_the_standards_has_its_2022_name_and_area(self):
        subjects=catalog.subjects(core.standards())
        self.assertEqual([s['id'] for s in subjects if s['group']=='기타' or s['name'].startswith('기타 과목')],[])
        names={s['id']:s['name'] for s in subjects}
        self.assertEqual((names['12경수'],names['12인수'],names['12로봇'],names['12심영']),('경제 수학','인공지능 수학','로봇과 공학세계','심화 영어'))

    def test_menu_keeps_each_subject_area_together(self):
        order=[s['group'] for s in catalog.subjects(core.standards())]
        runs=[g for i,g in enumerate(order) if i==0 or order[i-1]!=g]
        self.assertEqual(len(runs),len(set(runs)))
        self.assertEqual(runs[0],'국어')

    def test_codes_shared_by_two_subjects_keep_both_subjects_standards(self):
        # 12심독 (심화 영어 독해와 작문 · 심화 독일어) and 12스문 (스포츠 문화 · 스페인어권 문화) repeat 11 codes;
        # before 2026-10-30 the second subject silently replaced the first one's text.
        st=core.standards()
        english,german=st['[12심독01-01]'],st['[12심독01-01] (심화 독일어)']
        self.assertEqual((english['subject'],german['subject']),('12심독','12심독-독'))
        self.assertNotEqual(english['name'],german['name'])
        self.assertEqual(st['[12스문01-01] (스페인어권 문화)']['subject'],'12스문-스')
        self.assertTrue(all(catalog.subject_id(key)==v['subject'] for key,v in st.items()))
        self.assertEqual(catalog.official_code('[12심독01-01] (심화 독일어)'),'[12심독01-01]')
        names={s['id']:s['name'] for s in catalog.subjects(st)}
        self.assertEqual((names['12심독'],names['12심독-독'],names['12스문'],names['12스문-스']),('심화 영어 독해와 작문','심화 독일어','스포츠 문화','스페인어권 문화'))

    def test_middle_school_social_studies_is_one_subject_with_both_areas(self):
        # 교육부 고시 제2022-33호 [별책 3]: 지리 38 + 일반사회 36 standards, codes [9사(지리)..] and [9사(일사)..].
        st=core.standards();social={k:v for k,v in st.items() if v['subject']=='9사'}
        self.assertEqual((sum('(지리)' in k for k in social),sum('(일사)' in k for k in social)),(38,36))
        self.assertEqual(st['[9사(일사)08-02]']['note'][:16],'[9사(일사)08-02]에서는')   # printed as "08-2" in the notice
        self.assertEqual(catalog.subject_id('[9사(지리)09-04]'),'9사')
        self.assertEqual({s['id']:s['name'] for s in catalog.subjects(st)}['9사'],'사회 (중학교)')

class AddedSubjectsTests(unittest.TestCase):
    def test_subjects_missing_from_the_first_sheet_are_there(self):
        # 교육부 고시 제2022-33호 [별책 3]·[별책 4]와 대조해 2026-11-02 추가.
        counts={s['id']:s for s in catalog.subjects(core.standards())}
        for sid,name,n in (('12미적Ⅰ','미적분Ⅰ',20),('12미적Ⅱ','미적분Ⅱ',23),('12영Ⅰ','영어Ⅰ',16),('12영Ⅱ','영어Ⅱ',17),('12연극','연극',13),('9보','보건 (중학교)',26),('9진로','진로와 직업 (중학교)',14),('9환','환경 (중학교)',19)):
            self.assertEqual((counts[sid]['name'],counts[sid]['count']),(name,n))
        st=core.standards()
        self.assertEqual(catalog.subject_id('[12미적Ⅰ-02-03]'),'12미적Ⅰ')
        self.assertIn('$y=x^{n}$',st['[12미적Ⅰ-02-03]']['name'])                 # the equation the text export drops

class LegacyCardColumnTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(dir=core.ROOT/'.runtime')
    def tearDown(self): cleanup_tempdir(self.tmp)
    def test_card_files_with_the_old_symbol_column_still_import(self):
        # 2026-10-30: "글씨 프롬프트-물리량" became "글씨 프롬프트-기호·변수"; older card files keep working.
        c=core.blank_card(1);c.update(standard='[12대수01-01]',type='최선답형',difficulty='중',idea='지수의 성질',image_text_physics='$a^{m}$')
        path=Path(self.tmp.name)/'cards.xlsx';core.export_xlsx([c],path)
        wb=openpyxl.load_workbook(path);ws=wb['문항카드 생성']
        cell=next(cell for cell in ws[10] if cell.value=='글씨 프롬프트-기호·변수');cell.value='글씨 프롬프트-물리량'
        buf=io.BytesIO();wb.save(buf)
        self.assertEqual(core.import_cards(buf.getvalue())[0]['image_text_physics'],'$a^{m}$')

if __name__=='__main__':unittest.main()
