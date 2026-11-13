"""Read-only CLI workers: agents return JSON, the application applies validated results."""
from pathlib import Path
import copy
import json
import os
import re
import shutil
import subprocess
import threading
import time
from .core import ROOT, uid, now, atomic, image_prompt, SUBJECTIVE_TYPES
from . import runtime
from . import diagrams, diagrams_chart, diagrams_function, formats, maps, variants
from .catalog import GROUP_OF

PROCESSES={}
GUARD=threading.RLock()

def discover(provider):
    override=os.environ.get('QUESTION_MAKER_'+provider.upper()+'_PATH','')
    if provider!='codex' and override and Path(override).is_file(): return override
    if provider=='codex':
        per_user=runtime.user_root(ROOT)/'tools'/'codex'/'codex.exe'
        if per_user.is_file(): return str(per_user)
        if runtime.installed_mode():
            bundled=ROOT/'runtime'/'codex'/'codex.exe'
            if bundled.is_file(): return str(bundled)
            launcher_path=os.environ.get('QUESTION_STUDIO_CODEX_PATH','')
            if launcher_path and Path(launcher_path).is_file(): return launcher_path
        if override and Path(override).is_file(): return override
    found=shutil.which(provider+'.exe') or shutil.which(provider)
    if found and not found.lower().endswith(('.cmd','.bat')): return found
    if found and provider=='claude':
        package=Path(found).parent/'node_modules/@anthropic-ai/claude-code'
        for native in (package/'bin/claude.exe',package/'cli.js'):
            try:
                if native.is_file(): return str(native)
            except OSError: pass
    home=Path.home()
    try:
        candidates= list((home/'AppData/Local/OpenAI/Codex/bin').glob('*/codex.exe')) if provider=='codex' else [home/'.local/bin/claude.exe',home/'AppData/Roaming/npm/claude.cmd']
    except OSError:
        return None
    available=[]
    for path in candidates:
        try:
            if path.is_file():
                if path.suffix.lower()=='.cmd' and provider=='claude':
                    package=path.parent/'node_modules/@anthropic-ai/claude-code'
                    for native in (package/'bin/claude.exe',package/'cli.js'):
                        if native.is_file(): available.append((native.stat().st_mtime,native));break
                else: available.append((path.stat().st_mtime,path))
        except OSError:
            continue
    return str(max(available)[1]) if available else None

def command(provider, folder, schema, model='', images=()):
    exe=discover(provider)
    if not exe: raise ValueError(f'{provider} CLI가 없습니다. 먼저 설치하고 로그인해 주세요.')
    if images and provider!='codex': raise ValueError('기출 변형은 원본 그림을 함께 읽는 Codex CLI에서만 쓸 수 있습니다.')
    if provider=='codex':
        # 원본 그림은 다른 플래그 앞에 둔다. --image 는 값을 여러 개 받아서 끝의 '-'(stdin)까지 그림으로 읽을 수 있다.
        args=[exe,'exec',*[a for path in images for a in ('--image',str(path))],'--skip-git-repo-check','--sandbox','read-only','--color','never','--json','--output-schema',str(folder/'schema.json'),'-o',str(folder/'result.json')]
        if model: args+=['--model',model]
        args+=['-']
    elif provider=='claude':
        args=[exe,'-p','--output-format','json','--json-schema',json.dumps(schema,ensure_ascii=True),'--tools','','--no-session-persistence']
        if model: args+=['--model',model]
    else: raise ValueError('지원하지 않는 CLI입니다.')
    # Never interpolate card text into a shell command; the prompt goes through stdin.
    if exe.lower().endswith(('.cmd','.bat')):
        raise ValueError('Windows에서는 네이티브 CLI .exe 설치를 사용해 주세요. .cmd 셸 래퍼는 실행하지 않습니다.')
    if exe.lower().endswith('.js'):
        node=runtime.node_executable(ROOT)
        if not node: raise ValueError('npm 방식 CLI에는 Node.js가 필요합니다.')
        args=[node]+args
    return args

# A Codex turn writes nothing until it finishes (about 2 minutes), yet 3 of 16 runs on 2026-11-02 hung after
# "turn.started" until the 20-minute limit. A second attempt got through, so a silent run is restarted once.
STALL_SECONDS=420

class Stalled(Exception): pass

def failure_reason(provider, code, log):
    """종료 코드만으로는 알 수 없는 까닭을 작업 로그에서 찾아 교사에게 알린다."""
    try: text=Path(log).read_text(encoding='utf-8',errors='replace')
    except OSError: text=''
    if 'usage limit' in text.lower():
        found=re.search(r'try again at ([^".]+)',text)
        return f'{provider} 사용 한도에 도달했습니다.'+(f' {found[1]} 뒤에 이 문항만 다시 생성해 주세요.' if found else ' 한도가 풀린 뒤 이 문항만 다시 생성해 주세요.')
    return f'{provider} 종료 코드 {code}. 작업 로그에서 로그인·사용량·권한 상태를 확인해 주세요.'

def execute(provider, folder, prompt, schema, model='', cancel=None, images=()):
    try:
        return _execute(provider, folder, prompt, schema, model, cancel, images)
    except Stalled:
        pass
    try:
        return _execute(provider, folder, prompt, schema, model, cancel, images)
    except Stalled:
        raise ValueError(f'{provider} 응답이 {STALL_SECONDS//60}분 넘게 없어 두 번 시도한 뒤 멈췄습니다. 잠시 뒤 이 문항만 다시 생성해 주세요.') from None

def _execute(provider, folder, prompt, schema, model='', cancel=None, images=()):
    folder.mkdir(parents=True,exist_ok=True)
    atomic(folder/'schema.json',schema)
    (folder/'prompt.txt').write_text(prompt,encoding='utf-8')
    args=command(provider,folder,schema,model,images)
    env=(runtime.codex_environment(ROOT, executable=discover('codex')) if provider=='codex' and runtime.installed_mode()
         else runtime.node_environment(ROOT))
    env['PYTHONIOENCODING']='utf-8'
    env.setdefault('HOME',str(Path.home()))
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    with (folder/'events.log').open('w',encoding='utf-8') as log:
        p=subprocess.Popen(args,cwd=folder,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=flags)
        with GUARD: PROCESSES[folder.name]=p
        try:
            p.stdin.write(prompt.encode('utf-8')); p.stdin.close()
            started=time.monotonic()
            while p.poll() is None:
                if (cancel and cancel.is_set()) or time.monotonic()-started>1200:
                    stop_process(p)
                    raise ValueError('작업이 취소되었거나 20분 제한 시간을 초과했습니다.')
                if time.monotonic()-started>STALL_SECONDS and (folder/'events.log').stat().st_size<500:
                    stop_process(p)
                    raise Stalled()
                time.sleep(.3)
            if p.returncode:
                raise ValueError(failure_reason(provider,p.returncode,folder/'events.log'))
        finally:
            if p.poll() is None: stop_process(p)
            with GUARD: PROCESSES.pop(folder.name,None)
    if provider=='codex':
        return json.loads((folder/'result.json').read_text(encoding='utf-8-sig'))
    lines=(folder/'events.log').read_text(encoding='utf-8').splitlines()
    objects=[]
    for line in lines:
        try: objects.append(json.loads(line))
        except ValueError: pass
    result=next((v for v in reversed(objects) if isinstance(v,dict) and ('structured_output' in v or 'result' in v)),None)
    if not result or result.get('is_error'): raise ValueError('Claude 결과가 없거나 실패했습니다. 작업 로그를 확인해 주세요.')
    value=result.get('structured_output')
    if value is None: value=json.loads(result['result'])
    atomic(folder/'result.json',value)
    return value

def stop_process(p):
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    else: p.terminate()

def object_schema(props):
    return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}

CHECK=object_schema({k:{'type':'string'} for k in ('label','lhs','rhs')})
MATERIAL_SCHEMA=object_schema({
    'id':{'type':'string'},'kind':{'type':'string','enum':['image','text','table']},
    'label':{'type':'string'},'content':{'type':'string'},
    'image_mode':{'type':'string','enum':['','strict','mixed','flexible']},
    **{k:{'type':'string'} for k in ('image_locked','image_creative','image_text_physics','image_text_math','image_text_korean')},
    'image_text_none':{'type':'boolean'},'image_plan_version':{'type':'integer','enum':[2]}
})
QUESTION_SCHEMA=object_schema({**{k:{'type':'string'} for k in ['stem','material','question','statements','choices','explanation','concepts','review_note','image_locked','image_creative']},'image_mode':{'type':'string','enum':['','strict','mixed','flexible']},'answer':{'type':'integer','enum':[0,1,2,3,4,5]},'data_kind':{'type':'string','enum':['none','image','text','table']},'estimate':{'type':'number'},'discrimination':{'type':'number'},'calculation':{'type':'boolean'},'checks':{'type':'array','items':CHECK},'materials':{'type':'array','items':MATERIAL_SCHEMA}})
MATH_WRITING_RULE=('카드와 그림 글씨의 기호·변수·물리량·수식은 LaTeX로 작성하고 $...$로 감싼다. '
    '아래첨자와 위첨자는 각각 중괄호로 묶고, 곱해지는 변수·항은 서로 분리한다(예: $P_{0} V_{0}$, $v_{y}^{2}$). '
    '카드에 한글 native HWP 수식 SCRIPT 문법을 직접 쓰지 않는다. 한글 SCRIPT 변환은 HML 생성 단계에서 처리한다. '
    '단위와 한글 서술은 수식 밖에 둔다. 한글 자모·음운(ㄱ, ㅁ, ㅇ)과 발음 표기([궁물])는 수식이 아니므로 $...$로 감싸지 않는다. '
    '선분의 길이는 선분 기호를 붙여 쓴다: 식 속의 길이와 "~의 길이는?"은 $\\overline{AB}=12$, $\\overline{CE}$의 길이는?처럼 쓰고, '
    '도형 자체를 가리킬 때만 "선분 $AB$를 내분하는 점", "변 $BC$ 위의 점"처럼 기호 없이 쓴다.')
MATH_TEXT_DESCRIPTION=MATH_WRITING_RULE+' 예: $V_{0}$, $v_{y}$, $v=at$.'
for _field in ('stem','material','question','statements','choices','explanation','concepts'):
    QUESTION_SCHEMA['properties'][_field]['description']=MATH_TEXT_DESCRIPTION
MATERIAL_SCHEMA['properties']['content']['description']=MATH_TEXT_DESCRIPTION
# Underline marks a passage-set question asks for: the app inserts mark + [[text]] into the shared passage.
PASSAGE_MARK=object_schema({'label':{'type':'string'},'text':{'type':'string'},'mark':{'type':'string'}})
QUESTION_SCHEMA['properties']['passage_marks']={'type':'array','items':PASSAGE_MARK,
    'description':'지문 세트 문항에서 새 밑줄·기호가 필요할 때만 쓴다. label은 지문 이름표((가)·(나), 지문이 하나면 빈 문자열), text는 지문에 그대로 한 번만 나오는 구절, mark는 ㉠·㉡·ⓐ 같은 기호. 지문 세트가 아니면 빈 배열.'}
QUESTION_SCHEMA['required'].append('passage_marks')
# 서답형(단답형·서술형·논술형) 전용 필드. 선택형은 빈 값으로 둔다.
QUESTION_SCHEMA['properties'].update({
    'model_answer':{'type':'string','description':'서답형 모범 답안. '+MATH_WRITING_RULE+' 선택형이면 빈 문자열.'},
    'rubric':{'type':'string','description':'서답형 채점 기준. 요소별 배점과 감점 기준을 줄마다 쓴다. 선택형이면 빈 문자열.'},
    'conditions':{'type':'string','description':'서답형 답안 조건을 줄마다 하나씩 쓴다(예: 답안은 ‘~(이)다’로 끝나게 쓴다.). 없으면 빈 문자열.'},
    'partial_credit':{'type':'boolean','description':'서답형에 부분 점수가 있으면 true. 선택형이면 false.'}})
QUESTION_SCHEMA['required'].extend(['model_answer','rubric','conditions','partial_credit'])
IMAGE_SCHEMA=object_schema({'svg':{'type':'string'},'description':{'type':'string'},'constraints':{'type':'array','items':CHECK},'review_note':{'type':'string'}})

PLAN_SCHEMA=object_schema({**{k:{'type':'string'} for k in ('image_locked','image_creative','image_text_physics','image_text_math','image_text_korean')},'image_mode':{'type':'string','enum':['strict','mixed','flexible']}})
PLAN_SCHEMA['properties']['image_text_physics']['description']=MATH_WRITING_RULE+' 표시할 기호·변수·물리량·단위를 적는다.'
PLAN_SCHEMA['properties']['image_text_math']['description']=MATH_WRITING_RULE+' 표시할 수식을 적는다.'
QUESTION_SCHEMA['properties'].update({k:{'type':'string'} for k in ('image_text_physics','image_text_math','image_text_korean')})
QUESTION_SCHEMA['required']=list(QUESTION_SCHEMA['properties'])
LABEL_SCHEMA=object_schema({'kind':{'type':'string','enum':['physics','math','korean']},'text':{'type':'string'},**{k:{'type':'number'} for k in ('x','y','size','rotation')}})
LABELS_SCHEMA=object_schema({'labels':{'type':'array','items':LABEL_SCHEMA}})

def schema_for(kind, variant=False):
    if kind=='question' and variant:                       # 질문 스키마가 다 만들어진 뒤에 덧붙인다
        return object_schema({**QUESTION_SCHEMA['properties'],'variant_changes':{'type':'array','items':{'type':'string'}}})
    return {'question':QUESTION_SCHEMA,'image':IMAGE_SCHEMA,'plan':PLAN_SCHEMA,'labels':LABELS_SCHEMA}[kind]

IMAGE_POLICY = '''현재 그림·글씨 분리 규칙이 과거 지침의 라벨·문자 규칙보다 우선한다.
image_locked가 `지도:`로 시작하면 앱이 그리는 지도 명세이므로 내용을 그대로 두고 글씨 프롬프트는 비운다. `도식:`으로 시작하는 도식 명세도 같다.
과목 지침에 도식 종류가 있는 그림(물리의 역학 상황·회로·운동 그래프, 생명과학·화학 도식, 사회·과학의 수치 그래프, 수학의 함수 그래프)은 SVG 규칙을 쓰지 않고 image_locked에 `도식:` 명세를 쓴다. 앱이 평가원 그림 꼴로 그린다.
strict: image_locked에 SVG 규칙(또는 지도·도식 명세)만 작성한다. image_creative는 반드시 빈 문자열이다.
flexible: image_creative에 모든 시각 요소와 창작 조건을 작성한다. image_locked는 반드시 빈 문자열이다.
mixed: 두 영역 모두 작성하되 완전히 서로 다른 요소를 지정한다. 각 줄은 영문 요소ID: 설명 형식이다. 예: image_locked의 floor: 수평 바닥선 / image_creative의 ball: 공의 외관. 두 영역의 ID나 의미상 요소가 겹치면 안 된다. 같은 물체의 윤곽선을 두 영역에 반복해서 지시하지 않는다. 고정 요소와 창작 요소의 공간 관계를 제약으로 설명할 수 있으나 다른 영역 요소를 다시 그리도록 지시하면 안 된다.
모든 유형의 image_locked/image_creative에는 글씨·숫자·물리량·수식·단위·라벨을 표기하라는 지시를 절대 넣지 않는다. 길이비 1:2 같은 계산 조건은 사용할 수 있으나 그 값을 그림 위에 쓰지 않는다. material의 기존 글씨 지시를 위 두 영역에 복사하지 않는다.
필요한 글씨를 별도의 이미지 글씨 프롬프트로 분리한다: image_text_physics는 기호·변수·물리량·단위(LaTeX 표기), image_text_math는 수식(LaTeX 표기), image_text_korean은 한글·상황 설명(평문). 기호·수식은 LaTeX를 $...$로 감싸고 각 첨자를 중괄호로 쓰며 곱하는 변수를 분리한다(예: $P_{0} V_{0}$, $v_{y}^{2}$). 한글 native HWP SCRIPT는 카드·글씨 프롬프트에 직접 쓰지 않는다. 각각 정확히 표시할 내용, 기준 물체, 상대 위치를 작성한다. 필요 없으면 빈 문자열이다. 물체 이름 A/B, 패널 표기 (가)/(나), 축 이름과 눈금 숫자도 모두 글씨 레이어로 분리한다.
기호·수식의 글꼴은 Latin Modern Math, 한글은 신명 중명조이며, 실제 렌더링은 앱이 처리한다. 기본 그림에는 어떠한 글씨도 그리지 않는다. 글씨처럼 보이는 윤곽선을 path로 그리는 것도 금지한다.
교사가 image_mode를 선택했다면 바꾸지 않는다. 선택하지 않았으면 유형을 제안한다. 자료가 그림이 아니면 그림·글씨 프롬프트 필드는 전부 빈 문자열이다.
SVG 생성시 strict는 g id="geometry"만, flexible은 g id="illustration"만, mixed는 둘 모두 사용한다. mixed의 각 레이어 안에서 각 요소를 g data-element="요소ID"로 분리하고 프롬프트의 ID와 정확히 일치시킨다. 배경 흰 사각형 외에는 모든 시각 요소를 해당 그룹 안에 둔다. text/tspan은 사용하지 않는다. 좌표계는 viewBox="0 0 1000 640"이다.'''

# 자유롭게 그리는 그림(flexible, mixed의 창작 영역)도 앱이 그리는 도식과 같은 평가원 그림 꼴을 따른다(2026-11-11 교사 지정).
KICE_STYLE = """그림 꼴(모든 유형 공통, flexible과 mixed의 창작 영역 포함): 평가원 그림 문항처럼 그린다.
- 윤곽선은 검은 선(굵기 2.5 안팎), 보조선·숨은 선은 가는 선(1.5 안팎)이나 점선으로 굵기에 위계를 둔다.
- 색은 쓰지 않는다. 흰색·검정과 회색 두세 단계(#f2f2f2, #d9d9d9, #b3b3b3 안팎)만 쓴다.
- 입체감은 옅은 회색 음영으로만 준다(linearGradient·radialGradient를 쓸 수 있다). 구·원기둥은 한쪽이 밝은 회색 음영으로 그린다.
- 사물은 교과서·평가원 삽화처럼 단순하고 정돈된 선화로 그린다. 만화풍·사진풍·장식 무늬·떨어진 그림자·배경 풍경은 넣지 않는다.
- 문항 풀이에 필요한 것만 그리고, 그림은 칸에 알맞게 채우되 여백을 고르게 둔다."""


def _sections(text, level='## '):
    """Split a markdown document into (heading, body) pairs at the given heading level."""
    parts, head, body = [], '', []
    for line in text.splitlines():
        if line.startswith(level):
            parts.append((head, '\n'.join(body))); head, body = line[len(level):].strip(), [line]
        else:
            body.append(line)
    parts.append((head, '\n'.join(body)))
    return parts


ENGLISH_CHART = '''
영어 도표 문항: 그래프의 제목(title), 축 이름, 항목·범례 이름은 모두 영어로 쓴다(예: "title":"<Favorite Sports of Students>", "y":{"label":"(%)"}). 선택지는 그래프를 설명하는 영어 문장 다섯 개이고, 그래프에서 읽히는 값만으로 참거짓이 정해지게 한다.
'''

# Rules in 문항-문안-다듬기-지침.md written for physics items (상황 보존 사례, 좌표축, 단서 조항, 용어 표, 물리량 〈보기〉).
PHYSICS_PHRASING = ('1.5 ', '4. ', '5. ', '6. ', '9. ')


def question_instructions(subject_id='', written=False):
    """The writing guidance for one subject: item-type theory for everyone, plus that subject's style.
    Physics-specific phrasing rules and the teacher's class data go only to science subjects."""
    group = GROUP_OF.get(subject_id, '')
    science = group == '과학'
    read = lambda name: (ROOT / 'instructions' / name).read_text(encoding='utf-8')
    agent = read('과학수업-피드백-문항출제-에이전트-지침.md')
    agent = agent[agent.index('## 3. 평가 문항 작성 지침'):]           # item writing and review; not lesson feedback
    style = '\n\n'.join(body for head, body in _sections(read('교과별-문항-스타일.md')) if head in ('공통', group) or (written and head == '서답형'))
    phrasing = '\n\n'.join(body for head, body in _sections(read('문항-문안-다듬기-지침.md'))
                             if science or not head.startswith(PHYSICS_PHRASING))
    reference = '\n\n'.join(body for head, body in _sections(read('참조자료-제반사항.md'))
                              if head.startswith('2. ') or (science and head.startswith('1. ')))
    map_help = maps.PROMPT if group in ('사회', '과학') else ''
    if group == '과학': map_help += diagrams.PROMPT
    if group in ('사회', '과학'): map_help += diagrams_chart.PROMPT
    # 영어 도표 문항(수능 25번 꼴)도 앱이 그래프를 그린다(2026-11-12). 그래프 글씨는 영어로 쓴다.
    if group == '영어': map_help += diagrams_chart.PROMPT + ENGLISH_CHART
    if group == '수학': map_help += diagrams_function.PROMPT
    return '\n\n'.join(x for x in (agent, style, map_help, phrasing, reference) if x.strip())


def language_rule(subject_id=''):
    group = GROUP_OF.get(subject_id, '')
    if group == '영어':
        return '발문과 해설은 한국어로 쓰고, 지문·선택지·〈보기〉의 영어 문장은 영어로 쓴다.'
    if group == '제2외국어·한문':
        return '발문과 해설은 한국어로 쓰고, 지문·선택지에는 해당 언어(한문은 한자)를 그대로 쓴다.'
    return '문두·발문·보기·선택지·해설·자료 설명은 모두 한국어로 쓴다. 입력에 영어·중국어가 섞여 있어도 결과는 한국어다.'


def prompt_for(card, kind, feedback='', subject='', background_svg='', subject_id='', set_context=''):
    if kind=='image':
        # Deliberately omit the original material, question and text prompts so old labels cannot leak into the image.
        return f'시험용 글씨 없는 SVG 선화만 생성한다. JSON으로 응답한다.\n{IMAGE_POLICY}\n{image_prompt(card)}\n{KICE_STYLE}\n흰 바탕·충분한 여백. 외부 참조·script·style·image·use·foreignObject는 금지. constraints는 SVG에 실제로 쓴 좌표·길이 숫자만으로 만든 등식이다. x, y, width 같은 속성 이름이나 미지수는 쓰지 않고, 좌표쌍은 괄호로 묶어도 된다(예: lhs "(350+230, 280+160/2)", rhs "(580, 360)"). review_note는 사람이 확인할 기하 조건이다. 수정 요청도 글씨 없는 그림에만 적용한다.\n수정 요청: {feedback}'
    if kind=='labels':
        prompts={k:card.get(k,'') for k in ('image_text_physics','image_text_math','image_text_korean')}
        return f'다음 글씨 프롬프트만 편집 가능한 객체 목록으로 바꾼다. 그림 자체를 만들지 않는다.\n{json.dumps(prompts,ensure_ascii=False)}\n기존 글씨 객체(절대 중복 추가하지 말 것): {json.dumps(card.get("image_labels",[]),ensure_ascii=False)}\n배경 그림 SVG(좌표 배치 참고): {background_svg[:200000]}\n배경 설명: {image_prompt(card)}\nJSON labels 배열에 kind(physics/math/korean), text, x,y,size,rotation을 반환한다. 기호·수식은 LaTeX, 한글은 평문이다. 각각 독립 선택·이동 가능한 객체로 나눈다. x,y는 1000×640 캔버스의 글씨 상자 왼쪽 위 좌표, size는 8~120(기본 28), rotation은 -180~180도. 영역 밖·선 겹침을 피한다. 지정된 글씨가 없으면 빈 배열. 프롬프트에 없는 정답·설명은 추가하지 않는다.'
    instructions=question_instructions(subject_id,card.get('type') in SUBJECTIVE_TYPES) if kind=='question' else ''
    task='기존 문항 내용은 바꾸지 말고 material의 기존 이미지 프롬프트를 그림 프롬프트 두 영역과 글씨 프롬프트 세 종류로 분리·정리한다. 선택된 유형을 유지하고 해당 스키마 필드만 응답한다.' if kind=='plan' else ('교사 입력의 과목·성취기준·유형·난이도·아이디어를 보존하여 문항·상세해설을 작성한다. 배점(points)은 생성하지 않는다. 본문·자료·보기·선택지·해설의 기호·변수·물리량·수식은 항상 LaTeX로 작성한다. '+MATH_WRITING_RULE+' 답지는 ①~⑤ 다섯 줄, 짝짓기 열은 /로 구분. 계산은 calculation=true, checks에 Python식 + - * / ** sqrt sin cos tan Abs exp log(x) log(x, 밑) pi 등식(lhs/rhs)을 넣는다. estimate와 discrimination은 0~1. 자료는 순서가 있는 materials 배열에 image/text/table 블록으로 작성하며 필요하면 그림·글상자·표와 (가)(나) 그림을 한 문항에 함께 둔다. 각 블록의 id, 순서, kind, label, content를 기존 materials에서 그대로 보존하고, 기존 그림의 image_mode가 비어 있지 않으면 바꾸지 않는다. 새 블록은 id를 빈 문자열로 둔다. image에는 계획 프롬프트 필드만 작성하고 image, image_plan_approval, image_scene 등 승인·자산 상태는 만들지 않는다. 구형 호환 필드 material/data_kind는 첫 자료를 나타낸다. 그림이면 현재 분리 규칙을 적용한다. 글상자는 content를 본문으로 쓰고 자료 표는 content에 Markdown 표를 쓴다. review_note에는 교사 검토 사항을 정직하게 적는다.')
    prompt_card=copy.deepcopy(card)
    if kind=='question':
        from .core import material_blocks
        prompt_card.setdefault('authoring_mode','legacy')
        prompt_card.setdefault('materials_request','')
        prompt_card.setdefault('material_request_kinds',[])
        prompt_card.setdefault('material_request_image_mode','')
        prompt_card.setdefault('format','')
        blocks=[]
        allowed=('image_mode','image_locked','image_creative','image_text_physics','image_text_math','image_text_korean','image_text_none','image_plan_version')
        for block in material_blocks(card):
            item={k:copy.deepcopy(block.get(k,'')) for k in ('id','kind','label','content')}
            if block.get('kind')=='image':
                for key in allowed: item[key]=copy.deepcopy(block.get(key,False if key=='image_text_none' else 2 if key=='image_plan_version' else ''))
            blocks.append(item)
        prompt_card['materials']=blocks
        for key in ('image','image_plan_approval','image_labels','labels_initialized','image_scene'): prompt_card.pop(key,None)
    card_json=json.dumps(prompt_card,ensure_ascii=False)
    if kind=='question':
        kinds=prompt_card.get('material_request_kinds') or []
        kind_names={'image':'그림(image)','text':'글상자(text)','table':'표(table)'}
        kind_instruction=(
            '자료 종류는 AI가 문항에 맞게 판단한다.' if not kinds else
            '요청 자료 종류를 각각 최소 하나씩 결과 materials에 포함한다: '+', '.join(kind_names.get(k,k) for k in kinds)+
            '. 새 자료 블록은 선택한 종류로만 추가한다. 기존 자료에 선택하지 않은 종류가 있어도 그대로 유지하며, 같은 종류 자료가 이미 있으면 그 자료를 그대로 유지해 요청을 충족할 수 있다.'
        )
        requested_mode=prompt_card.get('material_request_image_mode') or ''
        mode_instruction=(
            f'새 그림과 그림 유형이 비어 있는 기존 그림에는 {requested_mode} 유형을 적용한다. 기존 그림에 이미 지정된 그림 유형은 그대로 보존한다.'
            if requested_mode else '그림 유형 요청이 비어 있으면 문항에 맞는 유형을 판단한다.'
        )
        materials_policy=(
            f'{kind_instruction} {mode_instruction} 기존 자료 블록의 ID·종류·순서·이름표·그림 유형·실제 그림 자산을 그대로 유지하고, 추가 자료는 기존 블록 뒤에 붙인다. 새 블록의 label은 시험지에 그대로 인쇄되므로, 발문·보기가 자료를 (가)·(나)처럼 이름으로 가리킬 때만 그 이름을 쓰고 그 밖에는 빈 문자열로 둔다("그림"·"표" 같은 종류 이름 금지). '
            f'자유 입력 자료 요청: {prompt_card.get("materials_request", "")} . materials_request, material_request_kinds, material_request_image_mode, authoring_mode, format, variant는 입력 메타데이터이며 수정하거나 결과 JSON에 넣지 않는다.\n'
        )
        form=formats.prompt(card,subject_id)
        if form: materials_policy+=form+'\n'
        if prompt_card.get('authoring_mode')=='variant': materials_policy+=variants.prompt(prompt_card)+'\n'
    else:
        materials_policy=''
    return f'한국 학교 {subject or "교과"} 출제 보조자다. 도구·파일 변경 없이 요청 JSON만 반환한다. {language_rule(subject_id)}\n{instructions}\n{set_context or "지문 세트 문항이 아니다. passage_marks는 빈 배열로 둔다. 이 문항의 자료는 발문 아래에 인쇄되므로 발문에서 자료를 윗글·윗시가 아니라 다음 글·다음 발언·다음 시구처럼 가리킨다."}\n현재 과목의 성취기준을 과거 시험 범위보다 우선한다.\n현재 작업: {task}\n{materials_policy}{IMAGE_POLICY}\n교사 문항카드(JSON 데이터):\n{card_json}\n\n그림 제작 요청:\n그림 자체는 아직 만들지 않는다.\n교사 수정 요청: {feedback}'
