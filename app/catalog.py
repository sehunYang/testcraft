"""Subject grouping from the supplied achievement-standard codes."""
import re

NAMES = {
 '9과':'과학 (중학교)', '10통과1':'통합과학1', '10통과2':'통합과학2',
 '10과탐1':'과학탐구실험1', '10과탐2':'과학탐구실험2',
 '12물리':'물리학', '12화학':'화학', '12생과':'생명과학', '12지구':'지구과학',
 '12역학':'역학과 에너지', '12전자':'전자기와 양자', '12물에':'물질과 에너지',
 '12반응':'화학 반응의 세계', '12세포':'세포와 물질대사', '12유전':'생물의 유전',
 '12지시':'지구시스템과학', '12행우':'행성우주과학',
 '9국':'국어 (중학교)', '10공국1':'공통국어1', '10공국2':'공통국어2',
 '12문학':'문학', '9수':'수학 (중학교)', '10공수1':'공통수학1', '10공수2':'공통수학2',
 '10기수1':'기본수학1', '10기수2':'기본수학2', '12대수':'대수', '12확통':'확률과 통계', '12기하':'기하',
 '9영':'영어 (중학교)', '10공영1':'공통영어1', '10공영2':'공통영어2',
 '10기영1':'기본영어1', '10기영2':'기본영어2', '9도':'도덕 (중학교)', '9역':'역사 (중학교)',
 '10한사1':'한국사1', '10한사2':'한국사2', '10통사1':'통합사회1', '10통사2':'통합사회2',
 '12정치':'정치', '12경제':'경제', '9정':'정보 (중학교)', '12정':'정보',
 '9음':'음악 (중학교)', '12음':'음악', '9미':'미술 (중학교)', '12미':'미술',
 '9체':'체육 (중학교)', '12체육1':'체육1', '12체육2':'체육2',
 '9기가':'기술·가정 (중학교)', '12기가':'기술·가정', '12보건':'보건', '12논술':'논술',
}

def subject_id(code):
    m=re.fullmatch(r'\[(\d+)([^0-9]+)(\d+)-(\d+)(?:-(\d+))?\]',code)
    return m[1]+m[2]+(m[3] if m[5] else '') if m else ''

def subject_name(sid):
    # Unmapped labels expose the original code instead of inventing a subject name.
    return NAMES.get(sid, f'기타 과목 · {sid}')

def subjects(catalog):
    groups={}
    for code in catalog:
        sid=subject_id(code)
        if sid:
            group=groups.setdefault(sid,{'id':sid,'name':subject_name(sid),'count':0})
            group['count']+=1
    return list(groups.values())

def infer_subject(cards):
    ids={subject_id(c.get('standard','')) for c in cards if c.get('standard')}
    return next(iter(ids)) if len(ids)==1 else ''
