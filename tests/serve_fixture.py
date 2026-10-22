"""Isolated browser-test server; never reads or modifies teachers' projects."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
from app import core, server, cli
LABEL_FAILURES=set()

def fake_execute(provider,folder,prompt,schema,model,cancel):
    import json
    import time
    time.sleep(4.0 if '테스트 취소 대기' in prompt else .35)
    if schema is cli.IMAGE_SCHEMA:
        return {'svg':'<svg viewBox="0 0 1000 640"><rect width="1000" height="640" fill="white"/><g id="geometry"><path d="M 90 440 H 920" stroke="black" stroke-width="3"/><rect x="290" y="270" width="220" height="170" fill="white" stroke="black" stroke-width="3"/><path d="M 560 340 H 790 L 765 327 M 790 340 L 765 353" fill="none" stroke="black" stroke-width="3"/></g></svg>','constraints':[],'review_note':'검증용 배경'}
    if schema is cli.LABELS_SCHEMA:
        if '테스트 글씨 한 번 실패' in prompt and folder.name not in LABEL_FAILURES:
            LABEL_FAILURES.add(folder.name)
            raise ValueError('검증용 글씨 배치 실패')
        return {'labels':[dict(kind='physics',text='v_0',x=620,y=270,size=28,rotation=0),dict(kind='math',text=r'\frac{1}{2}mv^2',x=140,y=130,size=32,rotation=0),dict(kind='korean',text='수평면',x=700,y=460,size=28,rotation=0)]}
    card=json.loads(prompt.split('교사 문항카드(JSON 데이터):\n')[1].split('\n\n그림 제작 요청:')[0])
    if schema is cli.PLAN_SCHEMA:
        return dict(image_mode=card.get('image_mode') or 'strict',image_locked='floor: 수평선과 상자 및 오른쪽 화살표',image_creative='',image_text_physics='상자 오른쪽 위 v_0',image_text_math='',image_text_korean='바닥 아래 수평면')
    if card['idea']=='테스트 실패': raise ValueError('검증용 실패')
    card.update(stem='실험 상황이다.',question='옳은 것은?',choices='① A\n② B\n③ C\n④ D\n⑤ E',answer=1,explanation='A가 옳다.',data_kind='none',material='',estimate=.5,discrimination=.3,calculation=False,checks=[],image_mode='',image_locked='',image_creative='')
    return {key:card[key] for key in cli.QUESTION_SCHEMA['properties']}

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='browser-fixture-',dir=core.ROOT/'.runtime') as tmp:
        core.DATA=Path(tmp)/'studio'
        # Browser tests must never consume the teacher's CLI allowance.
        cli.discover=lambda provider:'fixture-cli'
        cli.execute=fake_execute
        server.serve(8766)
