import copy
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
from app import core, server
from test_support import cleanup_tempdir

POEM='죽는 날까지 하늘을 우러러\n한 점 부끄럼이 없기를,\n\n잎새에 이는 바람에도\n나는 괴로워했다.'

def set_card(no,set_id,question='윗글에 대한 설명으로 적절한 것은?'):
    c=core.blank_card(no);c.update(standard='[12문학01-01]',type='최선답형',difficulty='중',idea='화자의 태도',
        question=question,choices='① 가\n② 나\n③ 다\n④ 라\n⑤ 마',answer=1,points='10',set_id=set_id)
    return c

class PassageSetTests(unittest.TestCase):
    def setUp(self):
        self.sid=core.uid();self.cards=[set_card(1,self.sid),set_card(2,self.sid,'㉠에 대한 이해로 적절한 것은?')]
        self.sets=[{'id':self.sid,'passages':[{'content':POEM,'source':'윤동주, 「서시」'}]}]

    def test_sets_validate_shape_and_keep_their_questions_together(self):
        sets=core.normalize_sets(self.sets,self.cards)
        self.assertEqual(sets[0]['passages'][0]['label'],'')                       # one passage needs no (가)
        two=core.normalize_sets([{'id':self.sid,'passages':[{'content':'가 글'},{'content':'나 글'}]}],self.cards)
        self.assertEqual([p['label'] for p in two[0]['passages']],['(가)','(나)'])
        apart=[self.cards[0],set_card(2,''),set_card(3,self.sid)]
        with self.assertRaisesRegex(ValueError,'이어지게'):core.normalize_sets(self.sets,apart)
        with self.assertRaisesRegex(ValueError,'지문 세트가 없습니다'):core.normalize_sets([],self.cards)
        self.assertEqual(core.normalize_sets(self.sets,[set_card(1,'')]),[])           # a set without questions is dropped

    def test_passage_prints_once_before_its_questions_with_underlines(self):
        from tools import gen
        sets=core.normalize_sets(self.sets,self.cards)
        sets[0]['passages'][0]['content']=sets[0]['passages'][0]['content'].replace('한 점 부끄럼','㉠[[한 점 부끄럼]]')
        with tempfile.TemporaryDirectory(dir=core.ROOT/'.runtime') as tmp:
            hml=gen.build(str(core.TEMPLATE),str(Path(tmp)/'set.hml'),tmp,title='지문 세트',records=server.cards_to_records(self.cards,sets))
        root=ET.fromstring(hml.split('?>',1)[1]);paragraphs=[''.join(p.itertext()).replace('∼','~') for p in root.iter('P')]   # gen prints ~ as ∼
        self.assertEqual(sum(p.startswith('【 1~2 】다음 글을 읽고 물음에 답하시오.') for p in paragraphs),1)
        self.assertEqual(hml.count('죽는 날까지 하늘을 우러러'),1)
        self.assertIn('- 윤동주, 「서시」 -',paragraphs)
        underlined=[t for t in root.iter('TEXT') if t.get('CharShape')=='42']
        self.assertEqual(''.join(''.join(t.itertext()) for t in underlined),'한 점 부끄럼')
        self.assertTrue(paragraphs.index('【 1~2 】다음 글을 읽고 물음에 답하시오.')<next(i for i,p in enumerate(paragraphs) if p.startswith('1.')))

    def test_marks_go_only_where_a_phrase_is_unique(self):
        passage_set=core.normalize_sets(self.sets,self.cards)[0]
        skipped=core.apply_passage_marks(passage_set,[{'label':'','text':'잎새에 이는 바람','mark':'㉠'},{'label':'','text':'는','mark':'㉡'},{'label':'','text':'없는 구절','mark':'㉢'}])
        self.assertIn('㉠[[잎새에 이는 바람]]',passage_set['passages'][0]['content'])
        self.assertEqual(skipped,['㉡ 는','㉢ 없는 구절'])                              # '는' occurs several times; the last is absent
        self.assertEqual(core.apply_passage_marks(passage_set,[{'label':'','text':'하늘','mark':'㉠'}]),['㉠ 하늘'])   # mark already used

    def test_ai_sees_the_passage_and_its_sibling_questions(self):
        exam={'cards':self.cards,'sets':core.normalize_sets(self.sets,self.cards)}
        context=core.set_context(exam,self.cards[1])
        self.assertIn('1~2번 지문 세트의 2번 문항',context);self.assertIn('죽는 날까지',context)
        self.assertIn('1번 [최선답형·중] 평가 요소: 화자의 태도 / 발문: 윗글에 대한 설명으로 적절한 것은?',context)

    def test_editing_a_passage_withdraws_the_approval(self):
        sets=core.normalize_sets(self.sets,self.cards)
        edited=copy.deepcopy(sets);edited[0]['passages'][0]['content']+='\n덧붙인 행'
        self.assertNotEqual(core.cards_digest(self.cards,sets),core.cards_digest(self.cards,edited))

    def test_cards_saved_before_sets_keep_their_hash(self):
        old=set_card(1,'');legacy=copy.deepcopy(old);legacy.pop('set_id')
        self.assertEqual(core.content_hash(old),core.content_hash(legacy))

if __name__=='__main__':unittest.main()
