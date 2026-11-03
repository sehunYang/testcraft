import datetime
import sys
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import literature

TODAY=datetime.date(2026,10,30)
WORKS={'서시':{'title':'서시','links':[{'ns':100,'title':'저자:윤동주'}],'categories':[]},
       '국경의 밤/서시':{'title':'국경의 밤/서시','links':[{'ns':100,'title':'저자:김동환'}],'categories':[]},
       '후대 시':{'title':'후대 시','links':[{'ns':100,'title':'저자:후대 시인'}],'categories':[]},
       '청산별곡':{'title':'청산별곡','categories':[{'title':'분류:PD-old'}]},
       '출처 미상':{'title':'출처 미상','categories':[]},
       '진달래꽃':{'title':'진달래꽃','links':[{'ns':100,'title':'저자:김소월'}],'pageprops':{'disambiguation':''}}}
PEOPLE={'저자:윤동주':{'title':'저자:윤동주','categories':[{'title':'분류:1917년 태어남'},{'title':'분류:1945년 죽음'}]},
        '저자:김동환':{'title':'저자:김동환','categories':[]},
        '저자:후대 시인':{'title':'저자:후대 시인','categories':[{'title':'분류:1975년 죽음'}]},
        '저자:김소월':{'title':'저자:김소월','categories':[{'title':'분류:1934년 죽음'}]}}
POEM_HTML='''<div class="mw-parser-output"><div class="ws-header ws-noexport"><span>저자: 윤동주</span></div>
<table class="messagebox"><tr><td>이 문서는 옛한글을 포함하고 있습니다.</td></tr></table>
<span class="pagenum ws-pagenum">15</span><div class="poem"><p>죽는 날까지 하늘을 우르러<br />
한점 부끄럼이 없기를,<sup class="reference">[1]</sup><br />
<br />
오늘 밤에도 별이 바람에 스치운다.
</p></div><div class="licenseContainer"><p>퍼블릭 도메인</p></div></div>'''

def fake_call(**params):
    if params.get('list')=='search':
        return {'query':{'search':[{'title':t,'snippet':'<span class="searchmatch">서시</span> 본문'} for t in WORKS]}}
    if params.get('action')=='parse':return {'parse':{'text':POEM_HTML}}
    table=PEOPLE if params['titles'].startswith('저자:') else WORKS
    return {'query':{'pages':[table[t] for t in params['titles'].split('|')]}}

class LiteratureTests(unittest.TestCase):
    def setUp(self):
        patcher=mock.patch.object(literature,'call',side_effect=fake_call);self.call=patcher.start();self.addCleanup(patcher.stop)

    def test_only_long_expired_authors_and_tagged_classics_are_allowed(self):
        found={r['title']:r for r in literature.search('서시',TODAY)['results']}
        self.assertTrue(found['서시']['allowed']);self.assertEqual(found['서시']['died'],1945)
        self.assertTrue(found['청산별곡']['allowed'])                                # anonymous, tagged PD-old
        self.assertFalse(found['국경의 밤/서시']['allowed']);self.assertIn('김동환',found['국경의 밤/서시']['reason'])   # death year unknown
        self.assertFalse(found['후대 시']['allowed']);self.assertIn('1975년',found['후대 시']['reason'])
        self.assertFalse(found['출처 미상']['allowed']);self.assertFalse(found['진달래꽃']['allowed'])
        self.assertEqual(found['서시']['snippet'],'서시 본문')

    def test_cutoff_follows_the_korean_term(self):
        self.assertEqual(literature.expired_before(TODAY),1962)                     # died before 1963: expired before 2013
        self.assertEqual(literature.expired_before(datetime.date(2040,1,1)),1969)  # life + 70 afterwards

    def test_text_keeps_lines_and_drops_page_furniture(self):
        text=literature.text('서시',TODAY)
        self.assertEqual(text['content'],'죽는 날까지 하늘을 우르러\n한점 부끄럼이 없기를,\n\n오늘 밤에도 별이 바람에 스치운다.')
        self.assertEqual(text['source'],'윤동주, 「서시」')
        self.assertEqual(literature.work_name('하늘과 바람과 별과 시 (1948년)/서시'),'서시')

    def test_the_server_rechecks_before_handing_out_text(self):
        with self.assertRaisesRegex(ValueError,'1975년'):literature.text('후대 시',TODAY)
        self.assertFalse(any(c.kwargs.get('action')=='parse' for c in self.call.call_args_list))

if __name__=='__main__':unittest.main()
