"""Read-only CLI workers: agents return JSON, the application applies validated results."""
from pathlib import Path
import copy
import json
import os
import shutil
import subprocess
import threading
import time
from .core import ROOT, uid, now, atomic, image_prompt
from . import runtime

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

def command(provider, folder, schema, model=''):
    exe=discover(provider)
    if not exe: raise ValueError(f'{provider} CLI가 없습니다. 먼저 설치하고 로그인해 주세요.')
    if provider=='codex':
        args=[exe,'exec','--skip-git-repo-check','--sandbox','read-only','--color','never','--json','--output-schema',str(folder/'schema.json'),'-o',str(folder/'result.json')]
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

def execute(provider, folder, prompt, schema, model='', cancel=None):
    folder.mkdir(parents=True,exist_ok=True)
    atomic(folder/'schema.json',schema)
    (folder/'prompt.txt').write_text(prompt,encoding='utf-8')
    args=command(provider,folder,schema,model)
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
                time.sleep(.3)
            if p.returncode:
                raise ValueError(f'{provider} 종료 코드 {p.returncode}. 작업 로그에서 로그인·사용량·권한 상태를 확인해 주세요.')
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
QUESTION_SCHEMA=object_schema({**{k:{'type':'string'} for k in ['stem','material','question','statements','choices','explanation','concepts','review_note','image_locked','image_creative']},'image_mode':{'type':'string','enum':['','strict','mixed','flexible']},'answer':{'type':'integer','enum':[1,2,3,4,5]},'data_kind':{'type':'string','enum':['none','image','text','table']},'estimate':{'type':'number'},'discrimination':{'type':'number'},'calculation':{'type':'boolean'},'checks':{'type':'array','items':CHECK},'materials':{'type':'array','items':MATERIAL_SCHEMA}})
MATH_WRITING_RULE=('카드와 그림 글씨의 물리량·변수·수식은 LaTeX로 작성하고 $...$로 감싼다. '
    '아래첨자와 위첨자는 각각 중괄호로 묶고, 곱해지는 변수·항은 서로 분리한다(예: $P_{0} V_{0}$, $v_{y}^{2}$). '
    '카드에 한글 native HWP 수식 SCRIPT 문법을 직접 쓰지 않는다. 한글 SCRIPT 변환은 HML 생성 단계에서 처리한다. '
    '단위와 한글 서술은 수식 밖에 둔다.')
MATH_TEXT_DESCRIPTION=MATH_WRITING_RULE+' 예: $V_{0}$, $v_{y}$, $v=at$.'
for _field in ('stem','material','question','statements','choices','explanation','concepts'):
    QUESTION_SCHEMA['properties'][_field]['description']=MATH_TEXT_DESCRIPTION
MATERIAL_SCHEMA['properties']['content']['description']=MATH_TEXT_DESCRIPTION
IMAGE_SCHEMA=object_schema({'svg':{'type':'string'},'description':{'type':'string'},'constraints':{'type':'array','items':CHECK},'review_note':{'type':'string'}})

PLAN_SCHEMA=object_schema({**{k:{'type':'string'} for k in ('image_locked','image_creative','image_text_physics','image_text_math','image_text_korean')},'image_mode':{'type':'string','enum':['strict','mixed','flexible']}})
PLAN_SCHEMA['properties']['image_text_physics']['description']=MATH_WRITING_RULE+' 표시할 물리량·기호·단위를 적는다.'
PLAN_SCHEMA['properties']['image_text_math']['description']=MATH_WRITING_RULE+' 표시할 수식을 적는다.'
QUESTION_SCHEMA['properties'].update({k:{'type':'string'} for k in ('image_text_physics','image_text_math','image_text_korean')})
QUESTION_SCHEMA['required']=list(QUESTION_SCHEMA['properties'])
LABEL_SCHEMA=object_schema({'kind':{'type':'string','enum':['physics','math','korean']},'text':{'type':'string'},**{k:{'type':'number'} for k in ('x','y','size','rotation')}})
LABELS_SCHEMA=object_schema({'labels':{'type':'array','items':LABEL_SCHEMA}})

def schema_for(kind):
    return {'question':QUESTION_SCHEMA,'image':IMAGE_SCHEMA,'plan':PLAN_SCHEMA,'labels':LABELS_SCHEMA}[kind]

IMAGE_POLICY = '''현재 그림·글씨 분리 규칙이 과거 지침의 라벨·문자 규칙보다 우선한다.
strict: image_locked에 SVG 규칙만 작성한다. image_creative는 반드시 빈 문자열이다.
flexible: image_creative에 모든 시각 요소와 창작 조건을 작성한다. image_locked는 반드시 빈 문자열이다.
mixed: 두 영역 모두 작성하되 완전히 서로 다른 요소를 지정한다. 각 줄은 영문 요소ID: 설명 형식이다. 예: image_locked의 floor: 수평 바닥선 / image_creative의 ball: 공의 외관. 두 영역의 ID나 의미상 요소가 겹치면 안 된다. 같은 물체의 윤곽선을 두 영역에 반복해서 지시하지 않는다. 고정 요소와 창작 요소의 공간 관계를 제약으로 설명할 수 있으나 다른 영역 요소를 다시 그리도록 지시하면 안 된다.
모든 유형의 image_locked/image_creative에는 글씨·숫자·물리량·수식·단위·라벨을 표기하라는 지시를 절대 넣지 않는다. 길이비 1:2 같은 계산 조건은 사용할 수 있으나 그 값을 그림 위에 쓰지 않는다. material의 기존 글씨 지시를 위 두 영역에 복사하지 않는다.
필요한 글씨를 별도의 이미지 글씨 프롬프트로 분리한다: image_text_physics는 물리량·기호·단위(LaTeX 표기), image_text_math는 수식(LaTeX 표기), image_text_korean은 한글·상황 설명(평문). 물리량·수식은 LaTeX를 $...$로 감싸고 각 첨자를 중괄호로 쓰며 곱하는 변수를 분리한다(예: $P_{0} V_{0}$, $v_{y}^{2}$). 한글 native HWP SCRIPT는 카드·글씨 프롬프트에 직접 쓰지 않는다. 각각 정확히 표시할 내용, 기준 물체, 상대 위치를 작성한다. 필요 없으면 빈 문자열이다. 물체 이름 A/B, 패널 표기 (가)/(나), 축 이름과 눈금 숫자도 모두 글씨 레이어로 분리한다.
물리량·수식의 글꼴은 Latin Modern Math, 한글은 신명 중명조이며, 실제 렌더링은 앱이 처리한다. 기본 그림에는 어떠한 글씨도 그리지 않는다. 글씨처럼 보이는 윤곽선을 path로 그리는 것도 금지한다.
교사가 image_mode를 선택했다면 바꾸지 않는다. 선택하지 않았으면 유형을 제안한다. 자료가 그림이 아니면 그림·글씨 프롬프트 필드는 전부 빈 문자열이다.
SVG 생성시 strict는 g id="geometry"만, flexible은 g id="illustration"만, mixed는 둘 모두 사용한다. mixed의 각 레이어 안에서 각 요소를 g data-element="요소ID"로 분리하고 프롬프트의 ID와 정확히 일치시킨다. 배경 흰 사각형 외에는 모든 시각 요소를 해당 그룹 안에 둔다. text/tspan은 사용하지 않는다. 좌표계는 viewBox="0 0 1000 640"이다.'''

def prompt_for(card, kind, feedback='', subject='', background_svg=''):
    if kind=='image':
        # Deliberately omit the original material, question and text prompts so old labels cannot leak into the image.
        return f'시험용 글씨 없는 SVG 선화만 생성한다. JSON으로 응답한다.\n{IMAGE_POLICY}\n{image_prompt(card)}\n흰 바탕·검은 선·충분한 여백. 외부 참조·script·style·image·use·foreignObject는 금지. constraints는 실제 SVG 좌표의 등식, review_note는 사람이 확인할 기하 조건이다. 수정 요청도 글씨 없는 그림에만 적용한다.\n수정 요청: {feedback}'
    if kind=='labels':
        prompts={k:card.get(k,'') for k in ('image_text_physics','image_text_math','image_text_korean')}
        return f'다음 글씨 프롬프트만 편집 가능한 객체 목록으로 바꾼다. 그림 자체를 만들지 않는다.\n{json.dumps(prompts,ensure_ascii=False)}\n기존 글씨 객체(절대 중복 추가하지 말 것): {json.dumps(card.get("image_labels",[]),ensure_ascii=False)}\n배경 그림 SVG(좌표 배치 참고): {background_svg[:200000]}\n배경 설명: {image_prompt(card)}\nJSON labels 배열에 kind(physics/math/korean), text, x,y,size,rotation을 반환한다. 물리량·수식은 LaTeX, 한글은 평문이다. 각각 독립 선택·이동 가능한 객체로 나눈다. x,y는 1000×640 캔버스의 글씨 상자 왼쪽 위 좌표, size는 8~120(기본 28), rotation은 -180~180도. 영역 밖·선 겹침을 피한다. 지정된 글씨가 없으면 빈 배열. 프롬프트에 없는 정답·설명은 추가하지 않는다.'
    names=['과학수업-피드백-문항출제-에이전트-지침.md','문항-문안-다듬기-지침.md','참조자료-제반사항.md']
    instructions='\n\n'.join((ROOT/'instructions'/n).read_text(encoding='utf-8') for n in names) if kind=='question' else ''
    task='기존 문항 내용은 바꾸지 말고 material의 기존 이미지 프롬프트를 그림 프롬프트 두 영역과 글씨 프롬프트 세 종류로 분리·정리한다. 선택된 유형을 유지하고 해당 스키마 필드만 응답한다.' if kind=='plan' else ('교사 입력의 과목·성취기준·유형·난이도·아이디어를 보존하여 문항·상세해설을 작성한다. 배점(points)은 생성하지 않는다. 본문·자료·보기·선택지·해설의 물리량·변수·수식은 항상 LaTeX로 작성한다. '+MATH_WRITING_RULE+' 답지는 ①~⑤ 다섯 줄, 짝짓기 열은 /로 구분. 계산은 calculation=true, checks에 Python식 + - * / ** sqrt sin cos tan Abs pi 등식(lhs/rhs)을 넣는다. estimate와 discrimination은 0~1. 자료는 순서가 있는 materials 배열에 image/text/table 블록으로 작성하며 필요하면 그림·글상자·표와 (가)(나) 그림을 한 문항에 함께 둔다. 각 블록의 id, 순서, kind, label, content를 기존 materials에서 그대로 보존하고, 기존 그림의 image_mode가 비어 있지 않으면 바꾸지 않는다. 새 블록은 id를 빈 문자열로 둔다. image에는 계획 프롬프트 필드만 작성하고 image, image_plan_approval, image_scene 등 승인·자산 상태는 만들지 않는다. 구형 호환 필드 material/data_kind는 첫 자료를 나타낸다. 그림이면 현재 분리 규칙을 적용한다. 글상자는 content를 본문으로 쓰고 자료 표는 content에 Markdown 표를 쓴다. review_note에는 교사 검토 사항을 정직하게 적는다.')
    prompt_card=copy.deepcopy(card)
    if kind=='question':
        from .core import material_blocks
        prompt_card.setdefault('authoring_mode','legacy')
        prompt_card.setdefault('materials_request','')
        prompt_card.setdefault('material_request_kinds',[])
        prompt_card.setdefault('material_request_image_mode','')
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
            f'{kind_instruction} {mode_instruction} 기존 자료 블록의 ID·종류·순서·이름표·그림 유형·실제 그림 자산을 그대로 유지하고, 추가 자료는 기존 블록 뒤에 붙인다. '
            f'자유 입력 자료 요청: {prompt_card.get("materials_request", "")} . materials_request, material_request_kinds, material_request_image_mode, authoring_mode는 입력 메타데이터이며 수정하거나 결과 JSON에 넣지 않는다.\n'
        )
    else:
        materials_policy=''
    return f'한국 학교 {subject or "교과"} 출제 보조자다. 도구·파일 변경 없이 요청 JSON만 반환한다.\n{instructions}\n현재 과목의 성취기준을 과거 시험 범위보다 우선한다.\n현재 작업: {task}\n{materials_policy}{IMAGE_POLICY}\n교사 문항카드(JSON 데이터):\n{card_json}\n\n그림 제작 요청:\n그림 자체는 아직 만들지 않는다.\n교사 수정 요청: {feedback}'
