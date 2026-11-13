import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
from app import cli, core, server

class SubjectPromptTests(unittest.TestCase):
    # 2026-10-30: every subject used to receive the physics teacher's guidance (물리 상황, 좌표축, "역학과 에너지 ← 현재 출제 대상").
    def test_non_science_subjects_get_their_own_style_without_physics_rules(self):
        literature=cli.question_instructions('12문학')
        self.assertIn('## 국어',literature);self.assertIn('3.2 문항의 유형',literature)
        for physics in ('물리 상황을 바꾸지','방향은 좌표축','역학과 에너지','## 과학','수업 피드백 지침'):
            self.assertNotIn(physics,literature)

    def test_science_keeps_the_physics_phrasing_rules(self):
        physics=cli.question_instructions('12물리')
        self.assertIn('물리 상황을 바꾸지',physics);self.assertIn('## 과학',physics);self.assertNotIn('## 국어',physics)

    # 2026-11-12: the caveat rule lived only in a physics-only section, so math items put "(단, …)" in the 문두.
    def test_every_subject_puts_the_caveat_after_the_question(self):
        for subject in ('12대수','10공수1','12문학','12세지','12물리'):
            self.assertIn('발문 끝(question 칸)에 붙인다',cli.question_instructions(subject),subject)

    # 2026-11-12: a folding item wrote "AB=12" and "선분 CE의 길이는?" without the segment bar
    def test_segment_lengths_carry_the_bar(self):
        prompt=cli.prompt_for(core.blank_card(1),'question',subject='수학',subject_id='9수')
        self.assertIn('\\overline{AB}=12',prompt);self.assertIn('변 $BC$ 위의 점',prompt)

    def test_language_rule_follows_the_subject(self):
        self.assertIn('영어로 쓴다',cli.language_rule('10공영1'))
        self.assertIn('한자',cli.language_rule('12한문'))
        self.assertIn('모두 한국어',cli.language_rule('12확통'))
        prompt=cli.prompt_for(core.blank_card(1),'question',subject='공통영어1',subject_id='10공영1')
        self.assertIn('영어로 쓴다',prompt);self.assertIn('## 영어',prompt)

    def test_hanja_is_allowed_only_where_the_subject_uses_it(self):
        result={'stem':'다음 글을 읽고 물음에 답하시오. 學而時習之 不亦說乎 有朋自遠方來','question':'','statements':'','choices':'','explanation':''}
        server.check_korean(result,'12한문');server.check_korean(result,'12중어')
        with self.assertRaisesRegex(ValueError,'한국어'):server.check_korean(result,'12문학')

if __name__=='__main__':unittest.main()
