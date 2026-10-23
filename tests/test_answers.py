import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from app.answers import build_answer_hml


class AnswerBookletTests(unittest.TestCase):
    def test_native_equations_summary_and_safe_text(self):
        cards=[{'no':1,'answer':2,'points':'100','difficulty':'상','standard':'[12역학01-01]',
                'standard_name':'운동','concepts':'역학',
                'explanation':r'**풀이**'+'\n'+r'곱은 $P_0 V_0$이고 속도는 v_y이다.'+'\n'+r'$$\frac{1}{2}mv^2$$'+'\n- 0~10초 <조건> & 결론'}]
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'answers.hml'
            root=ET.fromstring(build_answer_hml('시험 <예시> & 정답',cards,target))
        text=''.join(node.text or '' for node in root.iter('CHAR'))
        self.assertIn('시험 <예시> & 정답',text)
        self.assertIn('0∼10초 <조건> & 결론',text)
        self.assertNotIn('**',text)
        self.assertIn('정답 ②',text)
        scripts=[node.text for node in root.iter('SCRIPT')]
        self.assertEqual(len(scripts),3)
        self.assertTrue(all('\\' not in script for script in scripts))
        table=root.find('.//TABLE');rows=table.findall('ROW')
        self.assertEqual(len(rows),2)
        self.assertEqual([len(row.findall('CELL')) for row in rows],[5,5])
        page=root.find('.//PAGEDEF');margin=page.find('PAGEMARGIN')
        available=int(page.get('Width'))-int(margin.get('Left'))-int(margin.get('Right'))
        self.assertLessEqual(int(table.find('SHAPEOBJECT/SIZE').get('Width')),available)


if __name__=='__main__': unittest.main()
