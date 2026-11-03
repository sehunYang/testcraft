import copy
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
from app import answers, catalog, cli, core, server
from tools import gen

def choice(no,**kw):
    c=core.blank_card(no);c.update(standard='[12정치01-01]',type='최선답형',difficulty='중',idea='아이디어',question='옳은 것은?',
        choices='① 가\n② 나\n③ 다\n④ 라\n⑤ 마',answer=1,points='50',explanation='해설');c.update(kw)
    return c

def written(no,kind='서술형',**kw):
    c=core.blank_card(no);c.update(standard='[12정치01-01]',type=kind,difficulty='중',idea='아이디어',question='계산식을 서술하시오.',
        model_answer='모범 답안',rubric='요소별 2점',explanation='해설',points='50',**kw)
    return c

def printed(records,**kw):
    with tempfile.TemporaryDirectory(dir=core.ROOT/'.runtime') as tmp:
        hml=gen.build(str(core.TEMPLATE),str(Path(tmp)/'t.hml'),tmp,title='제목',records=records,**kw)
    return hml,ET.fromstring(hml.split('?>',1)[1])

def lines(root):
    return [''.join(p.itertext()).replace('∼','~') for p in root.find('BODY/SECTION').findall('P')]

class PaperLayoutTests(unittest.TestCase):
    def test_paper_is_b4_two_columns_with_school_and_subject_in_the_header(self):
        hml,root=printed(server.cards_to_records([choice(1),choice(2)]),school='해오름고등학교',subject='정치')
        page=root.find('.//PAGEDEF');self.assertEqual((page.get('Width'),page.get('Height')),('72852','103180'))
        self.assertEqual(root.find('.//COLDEF').get('Count'),'2')
        headers=list(root.iter('HEADER'));self.assertEqual([h.get('ApplyPageType') for h in headers],['Odd','Even'])
        for header in headers:
            text=''.join(header.itertext());self.assertIn('해오름고등학교',text);self.assertIn('정치',text)
        self.assertEqual({a.get('NumberType') for a in next(root.iter('FOOTER')).iter('AUTONUM')},{'Page','TotalPage'})
        self.assertIn('지적소유권은 해오름고등학교에',hml)
        self.assertNotIn('제목',' '.join(lines(root)[1:3]))                         # the exam title is not printed on the first line

    def test_template_holds_no_school_identity(self):
        text=(core.ROOT/'templates/학교양식_예시.hml').read_text(encoding='utf-8')
        self.assertIn('{학교명}',text);self.assertNotIn('고등학교에 있습니다',text);self.assertNotIn('<BINDATA',text)

    def test_without_a_school_name_no_box_and_no_ownership_notice(self):
        hml,root=printed(server.cards_to_records([choice(1),choice(2)]),subject='정치')
        self.assertNotIn('지적소유권',hml);self.assertNotIn('{학교명}',hml);self.assertNotIn('{과목명}',hml)
        self.assertIn('확인 사항',hml)
        self.assertNotIn('서답형 :',hml)                                             # no written questions, so that line goes

    def test_question_comes_before_material_unless_a_stem_leads(self):
        a=choice(1,data_kind='text',material='자료 글');b=choice(2,stem='상황 설명.',data_kind='text',material='자료 글')
        _,root=printed(server.cards_to_records([a,b]))
        section=[x for x in lines(root) if x.strip()]
        i=next(k for k,x in enumerate(section) if x.startswith('1.'));self.assertIn('옳은 것은? [50점]',section[i]);self.assertIn('자료 글',section[i+1])
        j=next(k for k,x in enumerate(section) if x.startswith('2.'));self.assertIn('상황 설명.',section[j]);self.assertIn('자료 글',section[j+1]);self.assertIn('옳은 것은? [50점]',section[j+2])

    def test_bogi_box_grows_with_statements_and_short_four_share_rows(self):
        for n in (2,3,4,5):
            items=[f'문장이 꽤 길어서 한 칸에 두 개가 들어가지 않는 보기 {i}번입니다.' for i in range(n)]
            table=gen.bogi_table(items);rows=table.findall('ROW')
            self.assertEqual(len(rows),n+3);self.assertEqual(table.get('RowCount'),str(n+3))
            text=''.join(table.itertext())
            for mark in 'ㄱㄴㄷㄹㅁ'[:n]:self.assertIn(mark+'.',text)
            self.assertEqual([c.get('RowSpan') for c in rows[2].findall('CELL') if int(c.get('RowSpan') or 1)>1],[str(n),str(n)])
        short=gen.bogi_table(['정당성','합법성','효율성','책임성']);self.assertEqual(short.get('ColCount'),'8')

class LineBreakTests(unittest.TestCase):
    def lines(self,text,width=11000):
        tokens=gen._tokens(text,gen.CS_BODY)
        return [(''.join(p[1] for t in line for p in t['parts']),pct) for line,pct in gen._lay_out(tokens,gen.CS_BODY,width,width,0)]

    def test_paragraphs_break_at_words_not_inside_them(self):
        self.assertIn('BreakNonLatinWord="false"',gen.HEAD);self.assertNotIn('BreakNonLatinWord="true"',gen.HEAD)

    def test_a_word_barely_over_squeezes_the_line(self):
        # 넷째 어절이 한 줄을 조금만 넘친다: 어절을 끌어와 자간을 줄인다.
        out=self.lines('가나다 라마바 사아자 차카타 파하가',width=18300)
        self.assertLess(out[0][1],0);self.assertGreaterEqual(out[0][1],-gen.SQUEEZE_MAX)
        self.assertTrue(out[0][0].strip().endswith('파하가'))

    def test_a_word_far_over_moves_down_and_the_line_widens(self):
        out=self.lines('가나다라 마바사아 자차카타파하가나다라마바사아',width=20*1100)
        self.assertEqual(out[0][0].strip(),'가나다라 마바사아')
        self.assertGreater(out[0][1],0);self.assertLessEqual(out[0][1],gen.WIDEN_MAX)
        self.assertEqual(out[-1][1],0)                                              # the last line keeps normal spacing

    def test_spacing_shapes_join_the_head_with_a_correct_count(self):
        hml,root=printed(server.cards_to_records([choice(1,stem='긴 문두가 여러 줄에 걸치도록 같은 말을 계속해서 되풀이하여 적어 줄이 넘어가게 만드는 문장을 씁니다. '*3)]))
        shapes=root.find('.//CHARSHAPELIST')
        self.assertEqual(int(shapes.get('Count')),len(shapes))
        self.assertEqual(len({s.get('Id') for s in shapes}),len(shapes))
        used={t.get('CharShape') for t in root.find('BODY/SECTION').iter('TEXT')}
        self.assertTrue(used<={s.get('Id') for s in shapes})

    def test_score_stays_inline_when_whole_and_goes_right_when_it_would_be_cut(self):
        short=gen.question_paragraphs(' 옳은 것은?','[3.5점]',gen.PS_ITEM,'1.')
        self.assertEqual(len(short),1);self.assertTrue(''.join(short[0].itertext()).endswith('[3.5점]'))
        wrapped=gen.question_paragraphs(' '+'다음 글에 대한 설명으로 옳은 것을 '*2+'고른 것은?','[3.5점]',gen.PS_ITEM,'1.')
        self.assertEqual(len(wrapped),1)                                            # wraps, but the score is whole: leave it
        full=gen.question_paragraphs(' '+'다음 글을 읽고 정부가 시장에 개입하는 근거와 그 한계를 각각 찾아 윗글의 내용과 관련지어 설명한 것으로 가장 적절한 것을 고른 것이 된 것은 무엇인가요?','[서술형-5.0점, 부분점수 있음.]',gen.PS_ITEM,'서답형 1.',tag_bold=True)
        self.assertEqual(len(full),2);self.assertEqual(full[1].get('ParaShape'),gen.PS_RIGHT)
        self.assertEqual(''.join(full[1].itertext()),'[서술형-5.0점, 부분점수 있음.]')

    def test_a_blank_line_separates_a_box_from_what_follows(self):
        info={'range':[1,1],'passages':[{'label':'','content':'지문','source':''}]}
        records=server.cards_to_records([choice(1)]);records[0][21]=info
        _,root=printed(records)
        body=root.find('BODY/SECTION').findall('P')
        box=next(i for i,p in enumerate(body) if i and p.find('.//TABLE') is not None and '지문' in ''.join(p.itertext()))
        self.assertTrue(gen.is_blank(body[box+1]));self.assertTrue(''.join(body[box+2].itertext()).startswith('1.'))

class QuestionWordingTests(unittest.TestCase):
    def test_situation_and_question_in_one_field_print_on_separate_lines(self):
        c=choice(1,question='다음은 갑과 을의 대화이다. 이에 대한 설명으로 옳은 것은?')
        section=[x for x in lines(printed(server.cards_to_records([c]))[1]) if x.strip()]
        i=next(k for k,x in enumerate(section) if x.startswith('1.'))
        self.assertEqual(section[i],'1. 다음은 갑과 을의 대화이다.');self.assertEqual(section[i+1],'이에 대한 설명으로 옳은 것은? [50점]')
        self.assertEqual(gen.split_question('다음 중 옳은 것은?'),('','다음 중 옳은 것은?'))
        self.assertEqual(gen.split_question('옳은 것은? (단, g는 상수이다.)')[0],'')

    def test_set_questions_are_told_not_to_repeat_the_header(self):
        sid=core.uid();a=choice(1,set_id=sid);b=choice(2,set_id=sid,question='다음 글을 읽고 옳은 것을 고른 것은?')
        exam={'cards':[a,b],'sets':[{'id':sid,'passages':[{'label':'','content':'글','source':''}]}],'subject':'12정치','title':'t'}
        self.assertIn('"다음 글을 읽고"를 쓰지 않는다',core.set_context(exam,a))
        self.assertTrue(any('2번: 세트 머리글과 겹칩니다' in w for w in core.validate(exam,phase='design')['warnings']))

    def test_ai_choices_move_shortest_first_with_answer_and_explanation(self):
        c=choice(1);c.update(choices='① 긴 선지 문장입니다 정말로\n② 짧다\n③ 중간 길이 선지\n④ 조금 더 긴 선지 문장\n⑤ 아주 긴 선지 문장입니다 정말로요',answer=2,explanation='②가 옳다. ①은 틀렸다.')
        core.order_choices(c)
        self.assertEqual(c['choices'].split('\n')[0],'① 짧다');self.assertEqual(c['answer'],1)
        self.assertEqual(c['explanation'],'①가 옳다. ④은 틀렸다.')
        self.assertFalse(core.choices_out_of_order(c['choices']))

    def test_values_and_formulas_keep_their_order(self):
        for choices in ('① $\\frac{1}{2}$\n② $1$\n③ $2$\n④ $3$\n⑤ $4$','① 1000\n② 200\n③ 30\n④ 4\n⑤ 5'):
            self.assertFalse(core.choices_out_of_order(choices))

    def test_english_and_table_choices_are_checked(self):
        self.assertTrue(core.choices_out_of_order('① the role of meaningful conversation\n② memorizing vocabulary every day\n③ repeated drills for long-term retention\n④ researchers who study languages\n⑤ why second languages are difficult'))
        c=choice(1);c.update(choices='A / B\n① 이산화탄소 / 염화수소수소\n② 철 / 황\n③ 구리 / 질산\n④ 마그네슘 / 염산\n⑤ 산화칼슘 / 염화수소',answer=1)
        core.order_choices(c);self.assertEqual(c['choices'].split('\n')[:2],['A / B','① 철 / 황']);self.assertEqual(c['answer'],5)

class StatementFormTests(unittest.TestCase):
    def test_a_statement_with_a_reason_is_flagged(self):
        statements='ㄱ. 가속도는 일정하다.\nㄴ. 합력이 0이므로 등속 운동한다.\nㄷ. 마찰이 있기 때문에 속력이 줄어든다.'
        self.assertEqual(core.reasoned_statements(statements),['ㄴ','ㄷ'])
        self.assertEqual(core.reasoned_statements('ㄱ. (나)의 시어는 극한 상황을 드러낸다.\nㄴ. 벗어나기 위해 순응하는 태도로 읽을 수 있다.'),[])
        self.assertEqual(core.reasoned_statements(''),[])

    def test_wording_that_leaves_a_gray_zone_is_flagged(self):
        self.assertEqual(core.vague_wording('ㄷ. 뷰렛을 헹구는 데 증류수가 적절하다.','① 바람직한 태도'),['바람직','적절'])
        self.assertEqual(core.vague_wording('ㄱ. 당량점에서 수용액은 염기성이다.','① ㄱ'),[])
        self.assertEqual(core.vague_wording('ㄱ. 고뇌로 읽을 수 있다.'),['읽을 수 있'])

    def test_statement_rules_apply_only_to_science_statements(self):
        def warned(subject,**fields):
            c=choice(1);c.update(**fields)
            return core.validate({'cards':[c],'sets':[],'subject':subject,'title':'t'},phase='design')['warnings']
        science=next(s for s,g in catalog.GROUP_OF.items() if g=='과학')
        self.assertTrue(any('효과적' in w for w in warned(science,statements='ㄱ. 이 방법이 효과적이다.')))
        self.assertTrue(any('이유가' in w for w in warned(science,statements='ㄱ. 합력이 0이므로 등속 운동한다.')))
        self.assertFalse(any('이유가' in w for w in warned(science,statements='ㄱ. 합력이 0이면 등속 운동한다.')))
        self.assertFalse(any('효과적' in w for w in warned(science,choices='① 효과적이다\n② b\n③ c\n④ d\n⑤ e')))
        self.assertFalse(any('효과적' in w or '이유가' in w for w in warned('12정치',statements='ㄱ. 합력이 0이므로 이 방법이 효과적이다.')))

class KeepAndLinesTests(unittest.TestCase):
    def test_stem_lines_stay_separate_and_a_question_is_kept_together(self):
        c=choice(1,stem='표는 농도를 나타낸 것이다.\n$\\mathrm{N}_{2}$ 반응이다.',data_kind='text',material='자료 글')
        hml,root=printed(server.cards_to_records([c,choice(2)]))
        section=[x for x in lines(root) if x.strip()]
        self.assertEqual(section[section.index('1. 표는 농도를 나타낸 것이다.')+1].strip()[-5:],'반응이다.')
        kept={p.get('Id') for p in root.find('.//PARASHAPELIST') if p.get('KeepWithNext')=='true'}
        body=root.find('BODY/SECTION').findall('P')
        first=next(i for i,p in enumerate(body) if ''.join(p.itertext()).startswith('1.'))
        self.assertIn(body[first].get('ParaShape'),kept)
        shapes=root.find('.//PARASHAPELIST');self.assertEqual(int(shapes.get('Count')),len(shapes))
        self.assertEqual({p.get('BreakNonLatinWord') for p in shapes},{'false'})   # every paragraph breaks only between words

    def test_the_blank_after_a_table_stays_with_its_question(self):
        c=choice(1,stem='표를 보시오.',data_kind='table',material='| 가 |\n|---|\n| 1 |')
        _,root=printed(server.cards_to_records([c,choice(2)]))
        kept={p.get('Id') for p in root.find('.//PARASHAPELIST') if p.get('KeepWithNext')=='true'}
        body=root.find('BODY/SECTION').findall('P')
        table=next(i for i,p in enumerate(body) if p.find('.//TABLE') is not None and i and '가' in ''.join(p.itertext()))
        self.assertIn(body[table].get('ParaShape'),kept);self.assertIn(body[table+1].get('ParaShape'),kept)

    def test_the_last_question_travels_with_the_end_table(self):
        _,root=printed(server.cards_to_records([choice(1),choice(2)]))
        kept={p.get('Id') for p in root.find('.//PARASHAPELIST') if p.get('KeepWithNext')=='true'}
        body=root.find('BODY/SECTION').findall('P')
        self.assertIn('확인 사항',''.join(body[-1].itertext()))  # 끝 표는 마지막 문항의 문단에 붙는다
        self.assertIn('④',''.join(body[-1].itertext()))
        self.assertIn(body[-2].get('ParaShape'),kept)

    def test_table_columns_follow_the_amount_of_text(self):
        widths=gen.table_widths([['구분','아주 긴 내용이 들어가는 칸입니다'],['가','짧은 내용']],2,30108)
        self.assertEqual(sum(widths),30108);self.assertGreater(widths[1],widths[0]*2)

    def test_a_short_text_box_is_not_split_but_a_long_one_may_be(self):
        def as_char(text):
            _,root=printed(server.cards_to_records([choice(1,data_kind='text',material=text)]))
            box=next(t for t in root.iter('TABLE') if text[:5] in ''.join(t.itertext()))
            return box.find('SHAPEOBJECT/POSITION').get('TreatAsChar')
        self.assertEqual(as_char('짧은 비평문입니다.'),'true')
        self.assertEqual(as_char('긴 비평문입니다. '*80),'false')

    def test_the_form_spelling_of_bogi_is_printed(self):
        hml,_=printed(server.cards_to_records([choice(1,question='옳은 것만을 〈보기〉에서 고른 것은?')]))
        self.assertIn('&lt;보기&gt;에서',hml);self.assertNotIn('〈보기〉',hml)

class TableBlockTests(unittest.TestCase):
    def test_text_around_a_table_is_printed_not_dropped(self):
        c=choice(1);c['materials']=[{'id':core.uid(),'kind':'table','label':'','content':'표준 용액의 농도는 0.1이다.\n\n| 측정 | 값 |\n|---|---:|\n| 1 | 2 |\n\n단위: mL'}]
        hml,_=printed(server.cards_to_records([c]))
        self.assertIn('표준 용액의 농도는 0.1이다.',hml);self.assertIn('단위: mL',hml)

class LongPairChoiceTests(unittest.TestCase):
    def test_long_pair_cells_stack_under_one_header(self):
        rows=[('maintained','reliable')]*5
        self.assertEqual(gen.stack_pairs('짝2',['(A)','(B)'],rows),'짝세로')
        tb=gen.stacked_pair_table(['(A)','(B)'],rows,ans=2)
        grid=[[''.join(c.itertext()).strip() for c in r.findall('CELL')] for r in tb.findall('ROW')]
        self.assertEqual(grid[0],['','(A)','(B)'])
        self.assertEqual(grid[2],['②','maintained','reliable'])
        self.assertEqual((tb.get('RowCount'),tb.get('ColCount')),('6','3'))
        widths={sum(int(c.get('Width')) for c in r.findall('CELL')) for r in tb.findall('ROW')}
        self.assertLessEqual(max(widths)-min(widths),2)
    def test_short_pair_cells_stay_in_the_pair_table(self):
        rows=[('높은','낮은','같은')]*5
        self.assertEqual(gen.stack_pairs('짝3',['(가)','(나)','(다)'],rows),'짝3')
    def test_short_data_table_does_not_split(self):
        so=gen.data_table([['a','b']]*3,keep=True).find('SHAPEOBJECT/POSITION')
        self.assertEqual(so.get('TreatAsChar'),'true')
        long_table=gen.data_table([['a','b']]*(gen.TABLE_KEEP_ROWS+1),keep=True).find('SHAPEOBJECT/POSITION')
        self.assertEqual(long_table.get('TreatAsChar'),'false')


class PipeTableTests(unittest.TestCase):
    def test_a_bar_inside_a_formula_is_not_a_cell_border(self):
        self.assertEqual(gen.parse_pipe('| 구분 | 식 |\n|---|---|\n| (가) | $|x-1|+|x+2|=3$ |'),[['구분','식'],['(가)','$|x-1|+|x+2|=3$']])

class FailureReasonTests(unittest.TestCase):
    def test_a_usage_limit_is_told_with_its_reset_time(self):
        with tempfile.TemporaryDirectory(dir=core.ROOT/'.runtime') as tmp:
            log=Path(tmp)/'events.log'
            log.write_text('{"type":"error","message":"You’ve hit your usage limit. Upgrade or try again at 11:21 PM."}',encoding='utf-8')
            self.assertEqual(cli.failure_reason('codex',1,log),'codex 사용 한도에 도달했습니다. 11:21 PM 뒤에 이 문항만 다시 생성해 주세요.')
            log.write_text('{"type":"error"}',encoding='utf-8')
            self.assertIn('종료 코드 1',cli.failure_reason('codex',1,log))

class StallTests(unittest.TestCase):
    def test_a_silent_run_is_restarted_once_then_reported(self):
        from unittest import mock
        with tempfile.TemporaryDirectory(dir=core.ROOT/'.runtime') as tmp:
            calls=[]
            def fake(*a,**k):
                calls.append(1)
                if len(calls)==1: raise cli.Stalled()
                return {'ok':True}
            with mock.patch.object(cli,'_execute',side_effect=fake):
                self.assertEqual(cli.execute('codex',Path(tmp),'p',{}),{'ok':True});self.assertEqual(len(calls),2)
            with mock.patch.object(cli,'_execute',side_effect=cli.Stalled()):
                with self.assertRaisesRegex(ValueError,'두 번 시도'):cli.execute('codex',Path(tmp),'p',{})

class EquationCommandTests(unittest.TestCase):
    def test_commands_met_in_the_subject_examples(self):
        from tools.hwp_equation import latex_to_hwp
        self.assertIn('DIVIDE',latex_to_hwp(r'\frac{16}{9}\div\frac{8}{3}'))
        self.assertIn('|',latex_to_hwp(r'P(B\mid A)'))
        self.assertIn('RLHARPOONS',latex_to_hwp(r'\mathrm{N}_{2}\rightleftharpoons 2\mathrm{NH}_{3}'))
        script=latex_to_hwp(r'\binom{8}{1}');self.assertIn('C',script);self.assertIn('8',script);self.assertNotIn('binom',script)

class WrittenQuestionTests(unittest.TestCase):
    def test_written_questions_print_their_own_number_and_score_form(self):
        cards=[choice(1),written(2,partial_credit=True,conditions='‘~(이)다’로 끝낸다.\n계산 과정을 쓴다.'),written(3,'단답형')]
        hml,root=printed(server.cards_to_records(cards),subject='정치')
        section=lines(root)
        self.assertTrue(any(x.startswith('서답형 1.') for x in section))
        self.assertIn('[서술형-50.0점, 부분점수 있음.]',section)                     # too long for its line, so it stands whole on the next
        self.assertTrue(any(x.startswith('서답형 2.') and '[단답형-50.0점]' in x for x in section))
        self.assertIn('◈ 계산 과정을 쓴다.',hml);self.assertIn('&lt;조 건&gt;',hml)
        self.assertIn('서답형 :',hml)

    def test_validation_asks_for_answer_key_not_choices(self):
        card=written(1);card.update(points='100',review_approved=True,model_answer='')
        report=core.validate({'cards':[card],'subject':'12정치','title':'t'},phase='design')
        codes={x['code'] for x in report['issues']}
        self.assertIn('model_answer_required',codes);self.assertNotIn('choices_format',codes);self.assertNotIn('answer_required',codes);self.assertNotIn('choices_required',codes)

    def test_written_cards_keep_no_answer_number(self):
        c=written(1);c['answer']=3
        self.assertEqual(core.normalize(c,1)['answer'],'')

    def test_written_questions_sort_after_choice_questions(self):
        cards=[written(1),choice(2),written(3),choice(4)]
        self.assertEqual([c['type'] for c in core.subjective_last(cards)],['최선답형','최선답형','서술형','서술형'])
        report=core.validate({'cards':[written(1),choice(2)],'subject':'12정치','title':'t'},phase='design')
        self.assertIn('written_order',{x['code'] for x in report['issues']})

    def test_a_passage_set_does_not_mix_choice_and_written(self):
        sid=core.uid();a=choice(1,set_id=sid);b=written(2,set_id=sid)
        with self.assertRaisesRegex(ValueError,'선택형끼리'):core.normalize_sets([{'id':sid,'passages':[{'content':'글'}]}],[a,b])

    def test_old_cards_keep_their_hash(self):
        old=choice(1);legacy=copy.deepcopy(old)
        for key in ('model_answer','rubric','conditions','partial_credit'):legacy.pop(key)
        self.assertEqual(core.content_hash(old),core.content_hash(legacy))

    def test_answer_booklet_gives_model_answer_and_rubric(self):
        with tempfile.TemporaryDirectory(dir=core.ROOT/'.runtime') as tmp:
            hml=answers.build_answer_hml('t',[choice(1),written(2,partial_credit=True)],Path(tmp)/'a.hml')
        root=ET.fromstring(hml.split('?>',1)[1]);text=' '.join(''.join(p.itertext()) for p in root.iter('P'))
        self.assertIn('서답형 1  ·  서술형  ·  50점',text);self.assertIn('부분 점수 있음',text);self.assertIn('모범 답안',text);self.assertIn('요소별 2점',text)
        self.assertEqual(root.find('.//PAGEDEF').get('Width'),'59528')              # the booklet stays A4

    def test_ai_gets_written_rules_only_for_written_cards(self):
        self.assertIn('## 서답형',cli.question_instructions('12정치',True))
        self.assertNotIn('## 서답형',cli.question_instructions('12정치',False))
        self.assertIn('model_answer',cli.QUESTION_SCHEMA['required'])

    def test_ai_result_for_a_written_card_clears_choices(self):
        c=written(1);c.update(model_answer='',rubric='',explanation='')
        result={k:'' for k in cli.QUESTION_SCHEMA['properties'] if cli.QUESTION_SCHEMA['properties'][k].get('type')=='string'}
        result.update(question='서술하시오.',explanation='해설',model_answer='답',rubric='기준',choices='① 가',answer=0,data_kind='none',estimate=.5,discrimination=.3,calculation=False,checks=[],materials=[],passage_marks=[],partial_credit=True,image_mode='')
        out=server.apply_question_result(c,result)
        self.assertEqual((out['choices'],out['answer'],out['model_answer'],out['partial_credit']),('','','답',True))
        result['model_answer']=''
        with self.assertRaisesRegex(ValueError,'모범 답안'):server.apply_question_result(written(1),result)

if __name__=='__main__':unittest.main()
