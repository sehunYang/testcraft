"""Opt-in real CLI integration test. Uses the user's existing CLI login."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
from app import core,cli,images

if __name__=='__main__':
    folder=core.ROOT/'.runtime/live-workflow'
    c=core.blank_card()
    c.update(standard='[12역학01-01]',standard_name='물체의 운동',difficulty='하',type='단일 정답형',points='4',idea='수평 직선 위에서 등속 운동하는 물체의 속력이 2 m/s이고 이동 시간이 3초인 상황에서 이동 거리를 묻는다. 자료 그림에는 물체, 수평면과 속도 화살표를 표시하고 정답 이동 거리는 표시하지 않는다.')
    result=cli.execute('codex',folder/'question',cli.prompt_for(c,'question'),cli.QUESTION_SCHEMA)
    c.update(result);c=core.normalize(c,1)
    assert c['data_kind']=='image',result
    assert c['answer'] in (1,2,3,4,5)
    assert c['checks'] and all(x['ok'] for x in core.verify_checks(c['checks'])),c['checks']
    picture=cli.execute('codex',folder/'image',cli.prompt_for(c,'image'),cli.IMAGE_SCHEMA)
    images.render_svg(picture['svg'],folder/'figure.png')
    core.atomic(folder/'card.json',c)
    core.atomic(folder/'image-review.json',picture)
    print(json.dumps({'question':'passed','image':'rendered','checks':core.verify_checks(c['checks']),'geometry':core.verify_checks(picture['constraints'])},ensure_ascii=False))
