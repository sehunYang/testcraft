"""Local-only application server. Start with python run_studio.py."""
import base64
import copy
import hashlib
import io
import json
import importlib.util
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
import traceback
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import core, cli, codex_setup, images, labels, runtime, vectors
from .catalog import subjects, subject_name
from .hwpx import validate_hwpx_package

TOKEN=secrets.token_urlsafe(32)
JOBS={}; CANCEL={}
ACTIVE={}
DUPLICATE_REQUESTS_MAX=20
HWP_CONVERSION_LOCK=threading.Lock()
EXPORT_DOCUMENTS=('시험지_학생용.hwpx','시험지_교사용.hwpx')
EXPORT_SUPPORT_FILES=('정답과해설.md','문항카드.xlsx','검수기록.json')
EXPORT_ARCHIVE='출제결과.zip'

def hwp_conversion_available():
    """Advertise conversion only when both pyhwpx and the HWP COM server are registered."""
    if os.name!='nt' or importlib.util.find_spec('pyhwpx') is None: return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,'HWPFrame.HwpObject'): return True
    except (ImportError,OSError): return False

def exam_for_client(exam):
    result=copy.deepcopy(exam)
    result['validation']=core.validate(result)
    result['card_validation']=core.validate(result,'cards')
    result['cards_approved']=core.cards_approved(result)
    result['content_digest']=core.export_digest(result)
    result['active_job']=ACTIVE.get(result['id'])
    return result

def read_project_snapshot(path):
    """Read a project JSON file without overlapping its replace-based writer."""
    with core.LOCK:
        return json.loads(Path(path).read_text(encoding='utf-8'))

def preserve_material_server_state(card, previous):
    """Never accept asset paths or explicit plan approvals from an API client."""
    old={block['id']:block for block in core.material_blocks(previous)}
    if card.get('materials') is None:
        card['image']=copy.deepcopy(previous.get('image'))
        card['image_plan_approval']=copy.deepcopy(previous.get('image_plan_approval'))
    else:
        for block in card['materials']:
            if block.get('kind')!='image': continue
            prior=old.get(block['id'])
            block['image']=copy.deepcopy(prior.get('image')) if prior and prior.get('kind')=='image' else None
            block['image_plan_approval']=copy.deepcopy(prior.get('image_plan_approval')) if prior and prior.get('kind')=='image' else None
            if not prior or prior.get('kind')!='image': block['image_scene']=None
        core.sync_material_aliases(card)
    card['review_approved']=bool(previous.get('review_approved'))
    previous_override=previous.get('calculation_override')
    if (previous_override and core.content_hash(card)==core.content_hash(previous)
            and core.calculation_override_active(card,previous_override)):
        card['calculation_override']=copy.deepcopy(previous_override)
    else:
        card['calculation_override']=None
    for block in core.material_blocks(card):
        if block.get('kind')!='image': continue
        projected,mid=core.material_projection(card,block['id'],require_image=True)
        prior=old.get(mid)
        if prior and prior.get('kind')=='image':
            old_projection,_=core.material_projection(previous,mid,require_image=True)
            if (projected.get('image') and projected['image'].get('approval_override')
                    and core.content_hash(old_projection)!=core.content_hash(projected)):
                projected['image'].pop('approval_override',None)
                projected['image']['approved']=False
            if core.image_plan_context(old_projection)!=core.image_plan_context(projected) and projected.get('image'):
                projected['image']['approved']=False
        if projected.get('image') and projected['image'].get('context')!=core.image_context(projected):
            projected['image']['approved']=False
        if projected.get('image') and projected['image'].get('final_digest')!=core.image_final_digest(projected):
            projected['image']['approved']=False
        if not core.image_plan_confirmed(projected): projected['image_plan_approval']=None
        core.sync_material_projection(card,projected,mid)
    return card

def preserve_authoring_metadata(card, raw, previous):
    """Keep new workflow fields stable when older clients omit them."""
    if previous:
        for key,default in (('authoring_mode','legacy'),('materials_request',''),('material_request_kinds',[]),
                            ('material_request_image_mode',''),('ai_requested',False)):
            if key not in raw: card[key]=previous.get(key,default)
    elif 'ai_requested' not in raw:
        # A new manual draft is never queued implicitly; AI and legacy blank
        # cards retain their historical pending flag.
        card['ai_requested']=card['authoring_mode']!='manual'
    return card

def image_material_targets(card, material_id=None, all_when_missing=False):
    blocks=[b for b in core.material_blocks(card) if b.get('kind')=='image']
    if material_id is not None:
        if not isinstance(material_id,str) or not re.fullmatch('[a-f0-9]{16}',material_id): raise ValueError('자료 블록 ID 오류')
        block=next((b for b in blocks if b.get('id')==material_id),None)
        if block is None: raise ValueError('요청한 그림 자료를 찾을 수 없습니다.')
        targets=[block]
    elif len(blocks)==1 or (all_when_missing and blocks): targets=blocks
    elif not blocks: raise ValueError('문항에 그림 자료가 없습니다.')
    else: raise ValueError('그림 자료가 여러 개입니다. material_id를 지정해 주세요.')
    return [(core.material_projection(card,b['id'],require_image=True)[0],b['id']) for b in targets]

def cards_to_records(cards):
    records=[]
    for card in cards:
        c=copy.deepcopy(card)
        if c['data_kind']=='none': c['material']=''
        elif c['data_kind']=='image': c['material']='자료 그림'
        elif c['data_kind']=='text' and not c['material'].startswith('(글상자)'): c['material']='(글상자)\n'+c['material']
        row=[None]*20
        for col,key in core.COLS.items(): row[col-1]=c.get(key,'')
        row.append(core.material_blocks(c))
        records.append(row)
    return records

def export_exam(exam, *, convert_hwpx=True):
    report=core.validate(exam)
    if not report['ready']: raise ValueError('출력 전 검토를 완료해 주세요: '+' / '.join(report['errors'][:8]))
    eid=exam['id']; folder=core.exam_path(eid)
    stamp=core.uid(); out=folder/'exports'/stamp; out.mkdir(parents=True)
    from tools import gen
    hml=gen.build(src=str(core.TEMPLATE),out=str(out/'문항지_초안.hml'),exam=str(folder),title=exam['title'],records=cards_to_records(exam['cards']))
    assets=[]
    for c in exam['cards']:
        for block in core.material_blocks(c):
            if block.get('kind')!='image': continue
            projection,_=core.material_projection(c,block['id'],require_image=True)
            im=block.get('image') or {}
            raw=asset_path(eid,im['final_file']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=im['final_sha256']: raise ValueError('확정된 그림 파일의 내용이 변경되었습니다.')
            assets.append((c['no'],block['id'],raw))
    for student,name in [(True,'시험지_학생용.hml'),(False,'시험지_교사용.hml')]:
        (out/name).write_text(images.embed(hml,assets,student),encoding='utf-8')
    lines=[f"# {exam['title']} — 정답 및 해설",'', '| 번호 | 정답 | 배점 | 난이도 |','|---|---|---|---|']
    lines += [f"| {c['no']} | {'①②③④⑤'[c['answer']-1]} | {c['points']} | {c['difficulty']} |" for c in exam['cards']]
    for c in exam['cards']:
        lines += ['',f"## {c['no']}번 · 정답 {'①②③④⑤'[c['answer']-1]} · {c['points']}점",f"성취기준: {c['standard']} {c['standard_name']}",f"내용 영역: {c['concepts']}",'',c['explanation']]
    lines+=['','## 출제 분포','','| 성취기준 | 문항 수 |','|---|---|']
    for standard in sorted(set(c['standard'] for c in exam['cards'])): lines.append(f"| {standard} | {sum(c['standard']==standard for c in exam['cards'])} |")
    lines+=['','## 문항별 내용 영역','','| 번호 | 내용 영역 |','|---|---|']+[f"| {c['no']} | {c['concepts']} |" for c in exam['cards']]
    (out/'정답과해설.md').write_text('\n'.join(lines),encoding='utf-8')
    core.export_xlsx(exam['cards'],out/'문항카드.xlsx')
    digest=core.export_digest(exam)
    core.atomic(out/'검수기록.json',{'created':core.now(),'revision':exam['revision'],'content_digest':digest,'report':report,'cards':exam['cards'],'hml_status':'XML·표·그림 검증 완료 / 한글 페이지 배치·수식 재계산 확인 필요'})
    bundle={'id':stamp,'created':core.now(),'revision':exam['revision'],'content_digest':digest}
    return refresh_export_bundle(out,bundle,convert_hwpx=convert_hwpx)

def _conversion(status,message):
    return {'status':status,'message':message}

def _write_conversion_audit(folder,conversion):
    path=folder/'검수기록.json'
    audit=json.loads(path.read_text(encoding='utf-8'))
    audit['conversion']=copy.deepcopy(conversion)
    audit['hml_status']='XML·표·그림 검증 완료 / '+conversion['message']
    core.atomic(path,audit)

def _published_export_files(folder,conversion):
    files=[name for name in EXPORT_SUPPORT_FILES if (folder/name).is_file()]
    if conversion.get('status')=='ready':
        files.extend(name for name in EXPORT_DOCUMENTS if (folder/name).is_file())
        if (folder/EXPORT_ARCHIVE).is_file(): files.append(EXPORT_ARCHIVE)
    return files

def _is_complete_published_export(folder,bundle):
    expected=[*EXPORT_DOCUMENTS,*EXPORT_SUPPORT_FILES]
    if not set([*expected,EXPORT_ARCHIVE]).issubset(set(bundle.get('files') or [])): return False
    try:
        for name in EXPORT_DOCUMENTS: validate_hwpx_package(folder/name)
        with zipfile.ZipFile(folder/EXPORT_ARCHIVE) as archive:
            if archive.testzip() is not None or set(archive.namelist())!=set(expected): return False
            for name in expected:
                if archive.read(name)!=(folder/name).read_bytes(): return False
    except (OSError,ValueError,zipfile.BadZipFile,KeyError):
        return False
    return True

def _backup_export_artifacts(folder):
    token=core.uid()
    names=(*EXPORT_DOCUMENTS,EXPORT_ARCHIVE,'검수기록.json')
    backups=[]
    try:
        for index,name in enumerate(names):
            source=folder/name
            backup=folder/f'.last-good-{token}-{index}.bak'
            shutil.copy2(source,backup)
            backups.append((name,backup))
    except Exception:
        for _,backup in backups: backup.unlink(missing_ok=True)
        raise
    return backups

def _restore_export_artifacts(folder,backups):
    errors=[]
    for name,backup in backups:
        try: os.replace(backup,folder/name)
        except OSError as exc: errors.append(f'{name}: {exc}')
    return errors

def _cleanup_export_backups(backups):
    for _,backup in backups:
        backup.unlink(missing_ok=True)

def _remove_published_hwpx(folder):
    for name in (*EXPORT_DOCUMENTS,EXPORT_ARCHIVE):
        try: (folder/name).unlink(missing_ok=True)
        except OSError: pass

def _tail(value,limit=500):
    if isinstance(value,bytes): value=value.decode('utf-8',errors='replace')
    return str(value or '')[-limit:].strip()

def _run_hwpx_conversion(folder):
    if not hwp_conversion_available():
        return _conversion('unavailable','이 PC에서 한글 자동 변환을 사용할 수 없습니다. Windows용 한컴오피스 한글 설치를 확인한 뒤 다시 연결해 주세요.')
    sources=[folder/'시험지_학생용.hml',folder/'시험지_교사용.hml']
    if not all(path.is_file() for path in sources):
        return _conversion('failed','변환할 학생용·교사용 HML 원본을 찾을 수 없습니다.')
    token=core.uid()
    staged=[folder/f'.hwpx-{token}-student.hwpx',folder/f'.hwpx-{token}-teacher.hwpx']
    command=[sys.executable,str(core.ROOT/'tools'/'수식크기_재계산.py'),'--batch',
             str(sources[0]),str(staged[0]),str(sources[1]),str(staged[1])]
    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    try:
        # Hancom COM is not safe to drive concurrently. One helper process
        # converts both outputs in sequence while this lock serializes bundles.
        with HWP_CONVERSION_LOCK:
            result=subprocess.run(command,capture_output=True,encoding='utf-8',errors='replace',
                                  timeout=180,creationflags=creationflags)
            if result.returncode:
                detail=' '.join(part for part in (_tail(result.stdout),_tail(result.stderr)) if part)
                raise RuntimeError(f'한글 변환 프로세스가 실패했습니다 (종료 코드 {result.returncode}). {detail}')
            validate_hwpx_package(staged[0],sources[0])
            validate_hwpx_package(staged[1],sources[1])
            if any(stage.stat().st_size == 0 for stage in staged):
                raise ValueError('변환된 HWPX 파일이 비어 있습니다.')
            final=[folder/name for name in EXPORT_DOCUMENTS]
            backups=[folder/f'.hwpx-{token}-backup-{index}.hwpx' for index in range(2)]
            saved=[]; promoted=[]
            try:
                for destination,backup in zip(final,backups):
                    if destination.exists():
                        os.replace(destination,backup); saved.append((destination,backup))
                for stage,destination in zip(staged,final):
                    os.replace(stage,destination); promoted.append(destination)
            except Exception:
                for destination in promoted:
                    destination.unlink(missing_ok=True)
                for destination,backup in reversed(saved):
                    if backup.exists(): os.replace(backup,destination)
                raise
            for _,backup in saved: backup.unlink(missing_ok=True)
        return _conversion('ready','학생용·교사용 HWPX 변환과 패키지 검증을 마쳤습니다.')
    except subprocess.TimeoutExpired as exc:
        detail=' '.join(part for part in (_tail(exc.stdout),_tail(exc.stderr)) if part)
        return _conversion('failed','한글 변환이 180초 안에 끝나지 않았습니다. 한글 상태를 확인한 뒤 다시 시도해 주세요. '+detail)
    except Exception as exc:
        return _conversion('failed',f'한글 HWPX 변환에 실패했습니다. 한글 상태를 확인한 뒤 다시 시도해 주세요. {exc}')
    finally:
        for path in staged: path.unlink(missing_ok=True)

def _build_export_zip(folder):
    expected=[*EXPORT_DOCUMENTS,*EXPORT_SUPPORT_FILES]
    missing=[name for name in expected if not (folder/name).is_file()]
    if missing: raise ValueError('ZIP에 넣을 출력 파일이 없습니다: '+', '.join(missing))
    for name in EXPORT_DOCUMENTS:
        validate_hwpx_package(folder/name)
    temporary=folder/f'.출제결과-{core.uid()}.partial.zip'
    destination=folder/EXPORT_ARCHIVE
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
            for name in expected: archive.write(folder/name,name)
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None or set(archive.namelist())!=set(expected):
                raise ValueError('출제결과 ZIP 검증에 실패했습니다.')
        os.replace(temporary,destination)
    finally:
        temporary.unlink(missing_ok=True)

def refresh_export_bundle(folder,bundle,*,convert_hwpx=True):
    previous_good=_is_complete_published_export(folder,bundle)
    backups=[]
    backup_error=None
    if previous_good:
        try: backups=_backup_export_artifacts(folder)
        except Exception as exc: backup_error=exc
    if backup_error is not None:
        conversion=_conversion('failed',f'기존 HWPX 파일을 보존하기 위한 백업에 실패해 변환을 시작하지 않았습니다. {backup_error}')
    elif not convert_hwpx:
        conversion=_conversion('pending','테스트에서 한글 자동 변환을 건너뛰었습니다.')
    else:
        conversion=_run_hwpx_conversion(folder)
    if conversion['status']=='ready':
        try:
            _write_conversion_audit(folder,conversion)
            _build_export_zip(folder)
        except Exception as exc:
            conversion=_conversion('failed',f'HWPX 묶음 ZIP을 만들지 못했습니다. HWPX 파일을 확인한 뒤 다시 시도해 주세요. {exc}')
    preserve_backups=False
    if conversion['status']!='ready':
        retry_error=conversion['message']
        if previous_good:
            restore_errors=_restore_export_artifacts(folder,backups) if backups else []
            if restore_errors:
                conversion['message']+=' 기존 정상 파일 복원 중 오류: '+' / '.join(restore_errors)
                preserve_backups=True
                _remove_published_hwpx(folder)
            else:
                conversion=_conversion('ready','재시도에 실패했지만 이전 정상 HWPX와 ZIP을 유지했습니다. '+retry_error)
                conversion['retry_error']=retry_error
        else:
            _remove_published_hwpx(folder)
            _write_conversion_audit(folder,conversion)
    if not preserve_backups: _cleanup_export_backups(backups)
    bundle['conversion']=conversion
    if conversion['status']=='ready':
        bundle['files']=_published_export_files(folder,conversion)
    elif previous_good and backups and not preserve_backups:
        bundle['files']=list(bundle.get('files') or [])
    else:
        bundle['files']=_published_export_files(folder,conversion)
    return bundle

def recalculate_export(exam,export_id):
    bundle=next((item for item in exam.get('exports',[]) if item.get('id')==export_id),None)
    if bundle is None: raise ValueError('출력 버전 오류')
    folder=core.exam_path(exam['id'])/'exports'/export_id
    if not folder.is_dir(): raise ValueError('출력 파일을 찾을 수 없습니다.')
    refresh_export_bundle(folder,bundle,convert_hwpx=True)
    return bundle

def asset_path(eid,name):
    if not re.fullmatch(r'[a-f0-9]{16}\.(png|svg)',name): raise ValueError('파일 이름 오류')
    return core.exam_path(eid)/'assets'/name

def duplicate_image_assets(eid,image,created_paths):
    """Copy a saved image's editable assets to fresh server-owned filenames."""
    if image is None: return None
    if not isinstance(image,dict): raise ValueError('그림 자료 형식 오류')
    if not image.get('file'): raise ValueError('복제할 그림 원본 파일 정보가 없습니다.')
    cloned=copy.deepcopy(image)
    digest_fields={'file':'sha256','edited_file':'edited_sha256'}
    for field in ('file','svg','edited_file','edited_svg'):
        name=image.get(field)
        if not name: continue
        source=asset_path(eid,name)
        if not source.is_file(): raise ValueError(f'복제할 그림 파일을 찾을 수 없습니다: {name}')
        digest_field=digest_fields.get(field)
        if digest_field and image.get(digest_field):
            actual=hashlib.sha256(source.read_bytes()).hexdigest()
            if actual!=image[digest_field]: raise ValueError(f'복제할 그림 파일이 변경되었습니다: {name}')
        while True:
            destination=asset_path(eid,core.uid()+source.suffix)
            try:
                with source.open('rb') as src, destination.open('xb') as dst:
                    created_paths.append(destination)
                    shutil.copyfileobj(src,dst)
                break
            except FileExistsError:
                continue
        cloned[field]=destination.name
        if digest_field and cloned.get(digest_field):
            cloned[digest_field]=hashlib.sha256(destination.read_bytes()).hexdigest()
    # Finalized artwork is an approval artifact. The clone must be approved
    # separately, so it keeps the editable source and labels only.
    for field in ('final_file','final_sha256','final_digest','approved_at','approval_artifact_digest'):
        cloned.pop(field,None)
    cloned['approved']=False
    cloned.pop('approval_override',None)
    return cloned

def duplicate_card_record(eid,exam,source_index,created_paths):
    source=exam['cards'][source_index]
    used={str(card.get('id')) for card in exam['cards']}
    for card in exam['cards']:
        used.update(str(block.get('id')) for block in core.material_blocks(card))
    def fresh_id():
        value=core.uid()
        while value in used: value=core.uid()
        used.add(value)
        return value

    clone=copy.deepcopy(source)
    clone['id']=fresh_id()
    clone['points']=''
    clone['review_approved']=False
    clone['ai_requested']=False
    clone['calculation_override']=None
    clone['image_plan_approval']=None
    if clone.get('materials') is None:
        if clone.get('data_kind')=='image':
            clone['image']=duplicate_image_assets(eid,clone.get('image'),created_paths)
            clone['image_plan_approval']=None
    else:
        for block in clone['materials']:
            block['id']=fresh_id()
            if block.get('kind')=='image':
                block['image']=duplicate_image_assets(eid,block.get('image'),created_paths)
                block['image_plan_approval']=None
        core.sync_material_aliases(clone)
    return clone

def remove_created_assets(paths):
    for path in paths:
        try: path.unlink(missing_ok=True)
        except OSError: pass

def make_image(eid,card,raw,svg=None,notes='',checks=None):
    aid=core.uid(); path=asset_path(eid,aid+'.png'); path.parent.mkdir(parents=True,exist_ok=True)
    if svg:
        images.validate_mode_layers(svg,card['image_mode'],card)
        images.render_svg(svg,path)
    else:
        from PIL import Image,ImageOps
        src=Image.open(io.BytesIO(images.normalize_png(raw)));src=ImageOps.contain(src,(1800,1152))
        canvas=Image.new('RGB',(1800,1152),'white');canvas.paste(src,((1800-src.width)//2,(1152-src.height)//2));canvas.save(path)
    card['image_scene']=None
    return {'file':path.name,'svg':aid+'.svg' if svg else None,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'context':core.image_context(card),'approved':False,'created':core.now(),'note':notes,'checks':core.image_check_results(checks or []),'mode':card['image_mode'],'layer_version':2}

def save_scene(eid,card):
    scene=card.get('image_scene');im=card.get('image')
    if scene is None:
        if im and im.get('edited_digest'):
            im['checks']=im.pop('original_checks',im.get('checks',[]))
            for key in ('edited_file','edited_svg','edited_sha256','edited_digest','edit_notice'):im.pop(key,None)
            im['approved']=False
        return
    if not im or scene['source_sha']!=im['sha256']:raise ValueError('그림 원본이 바뀌었습니다. 현재 그림을 다시 객체로 변환하세요.')
    digest=vectors.digest(scene)
    if im.get('edited_digest')==digest:return
    path=asset_path(eid,core.uid()+'.png')
    images.render_svg(vectors.to_svg(scene),path)
    im.update(edited_file=path.name,edited_svg=path.with_suffix('.svg').name,edited_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),edited_digest=digest,approved=False)
    im['original_checks']=im.get('original_checks',im.get('checks',[]))
    im['checks']=[]
    im['edit_notice']='객체 편집 후 길이·비례·배치를 직접 확인하고 최종 확정하세요. 생성 당시 검산은 편집 결과를 검증하지 않습니다.'

def finalize_image(eid,card,override_validation_digest=None):
    image_approval_preflight(eid,card)
    im=card.get('image')
    if not im or im.get('layer_version')!=2: raise ValueError('글씨 없는 배경 그림을 먼저 생성하거나 업로드하세요.')
    if not card.get('labels_initialized'): raise ValueError('글씨 프롬프트를 적용하거나 글씨 없이 확정을 선택하세요.')
    failed_checks=[x for x in core.image_check_results(im.get('checks') or []) if not x['ok']]
    validation_digest=core.image_validation_digest(card)
    if failed_checks and override_validation_digest!=validation_digest:
        raise ValueError('그림 제약 검사 결과를 확인하고 명시적으로 승인해 주세요.')
    base=asset_path(eid,im['file'])
    if hashlib.sha256(base.read_bytes()).hexdigest()!=im['sha256']: raise ValueError('배경 그림 파일이 변경되었습니다.')
    if card.get('image_scene') is not None:
        save_scene(eid,card)
        base=asset_path(eid,im['edited_file'])
        if hashlib.sha256(base.read_bytes()).hexdigest()!=im['edited_sha256']:raise ValueError('편집 그림 파일이 변경되었습니다.')
    path=asset_path(eid,core.uid()+'.png')
    labels.compose(base,card['image_labels'],path)
    im.update(final_file=path.name,final_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),final_digest=core.image_final_digest(card),approved=True)
    if failed_checks:
        override={
            'content_digest':core.content_hash(card),
            'context_digest':core.image_context(card),
            'validation_digest':validation_digest,
            'image_digest':core.image_final_digest(card),
            'approved_at':core.now(),
        }
        im['approval_override']=override
        override['artifact_digest']=core.image_approval_artifact_digest(card)
    else:
        im.pop('approval_override',None)


def image_approval_preflight(eid,card):
    """Check required image inputs and current assets before showing an override choice."""
    im=card.get('image')
    if not im or im.get('layer_version')!=2: raise ValueError('글씨 없는 배경 그림을 먼저 생성하거나 업로드하세요.')
    if not card.get('labels_initialized'): raise ValueError('글씨 프롬프트를 적용하거나 글씨 없이 확정하세요.')
    base=asset_path(eid,im['file'])
    if hashlib.sha256(base.read_bytes()).hexdigest()!=im.get('sha256'): raise ValueError('배경 그림 파일이 변경되었습니다.')
    if card.get('image_scene') is not None:
        save_scene(eid,card)
        im=card['image']
        edited=asset_path(eid,im['edited_file'])
        if hashlib.sha256(edited.read_bytes()).hexdigest()!=im.get('edited_sha256'): raise ValueError('편집 그림 파일이 변경되었습니다.')

def select_job_cards(exam,payload):
    if payload.get('card_ids') is not None:
        ids=payload.get('card_ids')
        if not isinstance(ids,list) or not ids or len(ids)>100 or any(not isinstance(x,str) or not re.fullmatch(r'[a-f0-9]{16}',x) for x in ids) or len(set(ids))!=len(ids):
            raise ValueError('재시도 문항 목록이 올바르지 않습니다.')
        wanted=set(ids);selected=[c for c in exam['cards'] if c['id'] in wanted]
        if len(selected)!=len(wanted): raise ValueError('재시도 대상 문항을 찾을 수 없습니다.')
    else:selected=[c for c in exam['cards'] if not payload.get('card_id') or c['id']==payload['card_id']]
    if payload['action'] in ('image','labels','plan'):
        if payload.get('material_id') is not None and not payload.get('card_id'):
            raise ValueError('material_id를 지정할 때는 card_id도 필요합니다.')
        selected=[c for c in selected if any(b.get('kind')=='image' for b in core.material_blocks(c))]
        for c in selected:
            targets=image_material_targets(c,payload.get('material_id'),all_when_missing=True)
            for projection,_ in targets:
                if payload['action']!='plan' and not core.image_plan_confirmed(projection): raise ValueError(f"{c['no']}번: 그림 유형과 제작 범위를 명시적으로 확인해 주세요.")
                if payload['action']=='labels' and not projection.get('image'): raise ValueError('먼저 배경 그림을 생성하세요.')
    else:
        explicit=bool(payload.get('card_id') or payload.get('card_ids') is not None)
        selected=[c for c in selected if c.get('ai_requested') is True
                  and (c.get('authoring_mode','legacy')!='manual' or explicit)]
    if not selected: raise ValueError('작업할 문항이 없습니다. 문항 생성은 AI 생성 요청이 Yes인 문항만 처리합니다.')
    return selected

def apply_question_result(card,result):
    original_card=copy.deepcopy(card)
    authoring_mode=card.get('authoring_mode','legacy')
    materials_request=card.get('materials_request','')
    material_request_kinds=core.normalize_material_request_kinds(card.get('material_request_kinds',[]))
    material_request_image_mode=core.normalize_material_request_image_mode(card.get('material_request_image_mode',''))
    core.validate_material_request_preferences(material_request_kinds,material_request_image_mode)
    original_blocks=core.material_blocks(card)
    original_explicit=card.get('materials') is not None
    for key in cli.QUESTION_SCHEMA['properties']:
        if key=='materials': continue
        if key not in result: raise ValueError('CLI 결과에 필요한 필드가 없습니다: '+key)
        card[key]=result[key]
    returned=result.get('materials')
    if returned is not None:
        if not isinstance(returned,list): raise ValueError('CLI 자료 블록 응답은 배열이어야 합니다.')
        if original_blocks and returned and len(returned)<len(original_blocks):
            raise ValueError('AI가 교사가 구성한 자료 블록을 누락했습니다. 결과를 적용하지 않았습니다.')
        if original_blocks and not returned and (original_explicit or any(c for c in original_blocks)):
            raise ValueError('AI가 기존 자료 블록을 누락했습니다. 결과를 적용하지 않았습니다.')
        if returned:
            updated=[]
            for index,item in enumerate(returned):
                if not isinstance(item,dict): raise ValueError('CLI 자료 블록 형식 오류')
                kind=item.get('kind'); label=str(item.get('label') or '').strip()
                prior=original_blocks[index] if index<len(original_blocks) else None
                if not prior and material_request_kinds and kind not in material_request_kinds:
                    raise ValueError('AI가 선택하지 않은 자료 종류를 새 블록으로 추가했습니다: '+str(kind))
                if prior:
                    if item.get('id')!=prior['id'] or kind!=prior['kind'] or label!=str(prior.get('label') or ''):
                        raise ValueError('AI가 기존 자료 블록의 ID·종류·순서를 변경했습니다. 결과를 적용하지 않았습니다.')
                block={'id':prior['id'] if prior else core.uid(),'kind':kind,'label':prior.get('label','') if prior else label,
                       'content':str(item.get('content') or '').strip()}
                if kind=='image':
                    for key in ('image_mode','image_locked','image_creative','image_text_physics','image_text_math','image_text_korean','image_text_none','image_plan_version'):
                        block[key]=item.get(key,False if key=='image_text_none' else 2 if key=='image_plan_version' else '')
                    if prior:
                        defaults={'image':None,'image_labels':[],'labels_initialized':False,'image_scene':None}
                        for key,default in defaults.items():
                            block[key]=copy.deepcopy(prior.get(key,default))
                        block['image_plan_approval']=copy.deepcopy(prior.get('image_plan_approval'))
                    else:
                        block.update(image=None,image_labels=[],labels_initialized=False,image_scene=None,image_plan_approval=None)
                updated.append(block)
            card['materials']=updated
        elif not original_explicit:
            card.pop('materials',None)
        elif original_explicit:
            card['materials']=[]
    elif original_explicit:
        # Old fixture/CLI schemas omit materials; preserve teacher-authored blocks.
        card['materials']=copy.deepcopy(card['materials'])
    elif not original_explicit and original_card.get('image_mode') and result.get('image_mode')!=original_card.get('image_mode'):
        raise ValueError('AI가 교사가 선택한 그림 유형을 변경했습니다. 결과를 적용하지 않았습니다.')
    if original_explicit and returned is None:
        core.sync_material_aliases(card)
    # Apply the selected plan to generated images and existing images whose
    # teacher-selected mode is blank. A nonblank prior mode is always kept.
    for block in core.material_blocks(card):
        if block.get('kind')!='image': continue
        prior=next((b for b in original_blocks if b.get('id')==block.get('id') and b.get('kind')=='image'),None)
        prior_mode=str((prior or {}).get('image_mode') or '').strip()
        returned_mode=str(block.get('image_mode') or '').strip()
        if prior_mode and returned_mode!=prior_mode:
            raise ValueError('AI가 교사가 선택한 그림 유형을 변경했습니다. 결과를 적용하지 않았습니다.')
        if material_request_image_mode and not prior_mode:
            if returned_mode and returned_mode!=material_request_image_mode:
                raise ValueError('AI가 요청한 새 그림 유형을 따르지 않았습니다. 결과를 적용하지 않았습니다.')
            if card.get('materials') is None:
                card['image_mode']=material_request_image_mode
            else:
                target=next(b for b in card['materials'] if b.get('id')==block.get('id'))
                target['image_mode']=material_request_image_mode
    if card.get('materials') is not None:
        core.sync_material_aliases(card)
    # These describe how the card is being authored and the one requested run;
    # they are not fields the model may rewrite as part of its draft.
    card['authoring_mode']=authoring_mode
    card['materials_request']=materials_request
    card['material_request_kinds']=material_request_kinds
    card['material_request_image_mode']=material_request_image_mode
    card=core.normalize(card,card['no'])
    card['image_plan_version']=2
    for key in ('estimate','discrimination'):
        if not isinstance(card[key],(int,float)) or not 0<=card[key]<=1: raise ValueError('난도·변별도 추정값 범위 오류')
    if not card['question'] or not card['explanation'] or re.findall('[①②③④⑤]',card['choices'])!=list('①②③④⑤'):
        raise ValueError('발문·해설·5개 답지를 갖추지 못한 응답입니다.')
    resulting_kinds={block.get('kind') for block in core.material_blocks(card)}
    missing_kinds=[kind for kind in material_request_kinds if kind not in resulting_kinds]
    if missing_kinds:
        raise ValueError('AI 응답에 요청한 자료 종류가 없습니다: '+', '.join(missing_kinds))
    for block in core.material_blocks(card):
        if block.get('kind')=='image':
            projected,_=core.material_projection(card,block['id'],require_image=True)
            plan_errors=core.image_plan_errors(projected)
            if plan_errors: raise ValueError('그림 계획 오류: '+' / '.join(plan_errors))
    card['ai_requested']=False
    card['review_approved']=False
    for block in core.material_blocks(card):
        if block.get('kind')!='image': continue
        projected,mid=core.material_projection(card,block['id'],require_image=True)
        prior=next((b for b in original_blocks if b.get('id')==mid and b.get('kind')=='image'),None)
        if prior:
            previous,_=core.material_projection(original_card,mid,require_image=True)
            if core.image_plan_context(previous)!=core.image_plan_context(projected):
                projected['image_plan_approval']=None
                if projected.get('image'): projected['image']['approved']=False
            if projected.get('image') and projected['image'].get('context')!=core.image_context(projected):
                projected['image']['approved']=False
            if projected.get('image') and projected['image'].get('final_digest')!=core.image_final_digest(projected):
                projected['image']['approved']=False
        else:
            projected['image_plan_approval']=None
            if projected.get('image'): projected['image']['approved']=False
        core.sync_material_projection(card,projected,mid)
    return card

def delete_exam(eid,title):
    if eid in ACTIVE: raise ValueError('작업을 취소하거나 완료한 후 작업실을 삭제해 주세요.')
    exam=core.read_exam(eid)
    if title!=exam['title']: raise ValueError('삭제할 작업실 이름이 일치하지 않습니다.')
    source=core.exam_path(eid).resolve()
    trash=(core.DATA.parent/'_studio_trash').resolve()
    destination=(trash/eid).resolve()
    if source.parent!=core.DATA.resolve() or destination.parent!=trash or destination.exists():
        raise ValueError('안전한 삭제 경로를 확인할 수 없습니다.')
    trash.mkdir(parents=True,exist_ok=True)
    core.atomic(source/'deleted.json',{'deleted_at':core.now(),'title':title})
    source.rename(destination)
    return {'deleted':eid,'recoverable':True}

def launch_job(eid, payload):
    with core.LOCK:
        if eid in ACTIVE: raise ValueError('이 회차에 진행 중인 작업이 있습니다.')
        exam=core.read_exam(eid)
        core.check_subject(exam['subject'],exam['cards'])
        action=payload.get('action')
        if action not in ('question','image','workflow','plan','labels'): raise ValueError('작업 유형 오류')
        if action in ('image','labels') and not core.cards_approved(exam): raise ValueError('문항카드를 먼저 전체 승인해 주세요. 승인 후 실제 그림을 생성합니다.')
        provider=payload.get('provider','codex')
        if runtime.installed_mode() and provider!='codex':
            raise ValueError('설치된 앱은 ChatGPT Codex 로그인으로만 생성 작업을 진행합니다.')
        if runtime.installed_mode() and not codex_setup.status().get('ready'):
            raise ValueError('유효한 유료 ChatGPT 플랜으로 로그인한 뒤 생성 작업을 진행해 주세요.')
        if provider not in ('codex','claude') or not cli.discover(provider): raise ValueError('선택한 CLI를 설치하고 로그인해 주세요.')
        selected=select_job_cards(exam,payload)
        kind='question' if action=='workflow' else action
        if kind=='question':
            for c in selected:
                if not all(c.get(k) for k in ('standard','type','difficulty','idea')): raise ValueError(f"{c['no']}번: 성취기준·유형·난이도·핵심 아이디어를 입력해 주세요.")
        if action in ('image','labels','plan'):
            targets=[(c,mid) for c in selected for _,mid in image_material_targets(c,payload.get('material_id'),all_when_missing=True)]
        else: targets=[(c,None) for c in selected]
        jid=core.uid(); cancel=threading.Event(); CANCEL[jid]=cancel; ACTIVE[eid]=jid
        job={'id':jid,'exam_id':eid,'status':'running','message':'CLI 준비 중','progress':0,'total':len(targets),'created':core.now(),'provider':provider,'action':action,'failed':[],'succeeded':0,
             'item_ids':list(dict.fromkeys(c['id'] for c,_ in targets)),'item_targets':[{'card_id':c['id'],'material_id':mid} for c,mid in targets]}
        JOBS[jid]=job
        folder=core.exam_path(eid)/'jobs'/jid
        core.atomic(folder/'job.json',job)
    def process_card(original,material_id=None):
        card=copy.deepcopy(original)
        if material_id is not None: card,_=core.material_projection(card,material_id,require_image=True)
        kind='question' if action=='workflow' else action
        label=next((b.get('label') for b in core.material_blocks(original) if b.get('id')==material_id),'') if material_id else ''
        item_name=f"{card['no']}번 {label} " if label else f"{card['no']}번 "
        job['message']=item_name+{'question':'문항·해설 생성 중','plan':'그림·글씨 프롬프트 분리 중','image':'글씨 없는 배경 생성 중','labels':'글씨 객체 배치 중'}[kind]
        core.atomic(folder/'job.json',job)
        stepfolder=folder/f"{card['id']}-{material_id+'-' if material_id else ''}{kind}"
        feedback=str(payload.get('feedback','')) or card.get('ai_feedback','')
        def execute(step):
            extra=asset_path(eid,card['image']['svg']).read_text(encoding='utf-8') if step=='labels' and (card.get('image') or {}).get('svg') else ''
            return cli.execute(provider,folder/f"{card['id']}-{material_id+'-' if material_id else ''}{step}",cli.prompt_for(card,step,feedback,subject_name(exam['subject']),extra),cli.schema_for(step),str(payload.get('model','')),cancel)
        def persist():
            with core.LOCK:
                current=core.read_exam(eid)
                index=next(j for j,c in enumerate(current['cards']) if c['id']==card['id'])
                if material_id is None: current['cards'][index]=card
                else:
                    current_card=current['cards'][index]
                    core.sync_material_projection(current_card,card,material_id)
                    current_card['review_approved']=bool(card.get('review_approved'))
                core.save_exam(current)
        result=execute(kind)
        if cancel.is_set(): raise ValueError('작업을 취소했습니다.')
        if kind=='question': card=apply_question_result(card,result)
        elif kind=='plan':
            chosen=card.get('image_mode')
            if chosen and result['image_mode']!=chosen: raise ValueError('교사가 선택한 그림 유형을 변경할 수 없습니다.')
            card.update({k:result[k] for k in cli.PLAN_SCHEMA['properties']});card['image_plan_version']=2
            errors=core.image_plan_errors(card)
            if errors: raise ValueError(' / '.join(errors))
            card['review_approved']=False;card['image_plan_approval']=None
            if card.get('image'): card['image']['approved']=False
        elif kind=='image':
            check_results=core.verify_checks(result.get('constraints',[]))
            card['image']=make_image(eid,card,None,svg=result['svg'],notes=result.get('review_note',''),checks=check_results)
            persist()  # Preserve the new background even if text creation fails.
        if kind=='image' and card.get('image_text_none') and not card.get('image_labels'):
            card['labels_initialized']=True;card['image']['approved']=False;persist()
        elif kind=='labels' or (kind=='image' and not card.get('labels_initialized')):
            job['message']=f"{card['no']}번 배경 완료 · 글씨 객체 배치 중"
            core.atomic(folder/'job.json',job)
            if kind!='labels': result=execute('labels')
            if cancel.is_set(): raise ValueError('작업을 취소했습니다. 배경 그림은 저장되어 있습니다.')
            existing=card.get('image_labels',[])
            additions=[dict(x,id=core.uid()) for x in result['labels']]
            card['image_labels']=labels.normalize_labels(existing+additions)
            card['labels_initialized']=True
            card['image']['approved']=False
        persist()

    def work():
        try:
            for i,(original,material_id) in enumerate(targets):
                if cancel.is_set(): raise ValueError('작업을 취소했습니다.')
                try:
                    process_card(original,material_id)
                    job['succeeded']+=1
                except Exception as e:
                    if cancel.is_set(): raise
                    job['failed'].append({'no':original['no'],'id':original['id'],'card_id':original['id'],'material_id':material_id,'error':str(e)})
                job['progress']=i+1
                core.atomic(folder/'job.json',job)
            if job['failed']:
                job.update(status='partial' if job['succeeded'] else 'failed',message=f"{job['succeeded']}문항 완료 · {len(job['failed'])}문항 실패. 실패한 문항은 Yes로 남아 있습니다." if action in ('question','workflow') else f"그림·글씨 {job['succeeded']}개 완료 · {len(job['failed'])}개 실패")
            else: job.update(status='completed',message='생성이 완료되었습니다. 완료된 문항의 AI 요청은 No로 변경했습니다.' if action in ('question','workflow') else '그림·글씨 작업이 완료되었습니다. 내용을 검토해 주세요.')
        except BaseException as e:
            job.update(status='cancelled' if cancel.is_set() else 'failed',message=str(e))
        finally:
            with core.LOCK:
                ACTIVE.pop(eid,None); CANCEL.pop(jid,None)
                core.atomic(folder/'job.json',job)
    threading.Thread(target=work,daemon=True).start()
    return job

class Handler(BaseHTTPRequestHandler):
    server_version='TestCraft/1.1'
    def log_message(self,*args): pass

    def send(self,value,status=200,content_type='application/json; charset=utf-8'):
        raw=json.dumps(value,ensure_ascii=False).encode() if isinstance(value,(dict,list)) else value
        if isinstance(raw,str): raw=raw.encode()
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(raw)

    def check_host(self):
        host=self.headers.get('Host','').split(':')[0]
        if host not in ('127.0.0.1','localhost'): raise ValueError('로컬 접속만 허용됩니다.')

    def do_GET(self):
        try:
            self.check_host()
            url=urllib.parse.urlsplit(self.path); p=urllib.parse.unquote(url.path)
            q=urllib.parse.parse_qs(url.query)
            if p=='/api/health':
                self.send({'identity':runtime.APP_ID,'version':runtime.APP_VERSION,
                           'data_dir':str(core.DATA.resolve())}); return
            if p=='/api/codex/status': self.send(codex_setup.status()); return
            if p=='/api/bootstrap':
                projects=[]
                for f in core.DATA.glob('*/project.json'):
                    try: e=read_project_snapshot(f)
                    except FileNotFoundError: continue
                    cards=e.get('cards',[])
                    review_remaining=sum(not c.get('review_approved') for c in cards)
                    image_blocks=[(c, b) for c in cards for b in core.material_blocks(c) if b.get('kind')=='image']
                    image_total=len(image_blocks)
                    image_remaining=sum(not (b.get('image') or {}).get('approved') for _, b in image_blocks)
                    if review_remaining: next_action=f'검토 {review_remaining}개 남음'
                    elif not core.cards_approved(e): next_action='출제안 승인'
                    elif image_remaining: next_action=f'그림 {image_remaining}개 남음'
                    else:
                        validation=core.validate(e)
                        next_action='시험지 받기' if validation['ready'] else f'{len(validation["issues"])}개 확인 필요'
                    projects.append({'id':e['id'],'title':e['title'],'updated':e['updated'],'subject':e.get('subject',''),
                                     'card_count':len(cards),'review_remaining':review_remaining,'image_remaining':image_remaining,
                                     'image_total':image_total,
                                     'next_action':next_action})
                legacy=[str(f.relative_to(core.ROOT)).replace('\\','/') for f in (core.ROOT/'exams').glob('*/02_card/*.xlsx')]
                self.send({'identity':runtime.APP_ID,'version':runtime.APP_VERSION,
                           'data_dir':str(core.DATA.resolve()),'installed':runtime.installed_mode(),
                           'codex':codex_setup.status(),'token':TOKEN,
                           'exams':sorted(projects,key=lambda x:x['updated'],reverse=True),'types':core.TYPES,
                           'subjects':subjects(core.standards()),'cli':{p:bool(cli.discover(p)) for p in ('codex','claude')},
                           'hwp_conversion_available':hwp_conversion_available(),'legacy':legacy}); return
            if p=='/api/standards': self.send(core.standards()); return
            if p.startswith('/label-assets/'):
                name=p.split('/')[-1]
                if not re.fullmatch('[a-f0-9]{64}\\.png',name): raise ValueError('글씨 파일 이름 오류')
                self.send((labels.CACHE/name).read_bytes(),content_type='image/png');return
            if p.startswith('/api/exams/'):
                eid=p.split('/')[3]; e=core.read_exam(eid)
                self.send(exam_for_client(e)); return
            if p.startswith('/api/jobs/'):
                jid=p.split('/')[3]
                if not re.fullmatch('[a-f0-9]{16}',jid): raise ValueError('작업 ID 오류')
                paths=list(core.DATA.glob(f'*/jobs/{jid}/job.json'))
                if not paths: raise ValueError('작업이 없습니다.')
                job=copy.deepcopy(JOBS.get(jid) or json.loads(paths[0].read_text(encoding='utf-8')))
                if job['status']=='running' and jid not in JOBS: job.update(status='interrupted',message='앱 재시작으로 중단되었습니다. 완료된 문항은 저장되어 있습니다.')
                logs=list(paths[0].parent.glob('*/events.log'))
                job['log']='\n'.join(f.read_text(encoding='utf-8',errors='replace')[-7000:] for f in sorted(logs,key=lambda p:p.stat().st_mtime)[-2:])
                self.send(job); return
            if p=='/api/library':
                files=list((core.ROOT/'reference/image-workflow/png/hml_text_2_5x_pass').glob('*.png'))
                self.send([{'id':f.stem,'name':f.name} for f in files]); return
            if p.startswith('/library/'):
                name=p[len('/library/'):]
                if Path(name).name!=name or '/' in name or '\\' in name: raise ValueError('파일 오류')
                self.send((core.ROOT/'reference/image-workflow/png/hml_text_2_5x_pass'/name).read_bytes(),content_type='image/png'); return
            if p.startswith('/assets/'):
                _,_,eid,name=p.split('/')
                self.send(asset_path(eid,name).read_bytes(),content_type='image/svg+xml' if name.endswith('.svg') else 'image/png'); return
            if p.startswith('/download/'):
                parts=p.split('/'); eid,rid,name=parts[2:]
                if not re.fullmatch('[a-f0-9]{16}',rid) or Path(name).name!=name or '\\' in name: raise ValueError('경로 오류')
                exam=core.read_exam(eid)
                bundle=next((item for item in exam.get('exports',[]) if item.get('id')==rid),None)
                if bundle is None or name not in bundle.get('files',[]):
                    self.send({'error':'요청한 파일은 공개된 출력물이 아닙니다.'},404); return
                f=core.exam_path(eid)/'exports'/rid/name
                if not f.is_file(): self.send({'error':'출력 파일을 찾을 수 없습니다.'},404); return
                self.send_response(200); self.send_header('Content-Type','application/octet-stream'); self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(name)); self.send_header('Content-Length',str(f.stat().st_size)); self.end_headers(); self.wfile.write(f.read_bytes()); return
            if p=='/template':
                self.send(core.TEMPLATE.read_bytes(),content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'); return
            static={'/image-flow.js':'image-flow.js','/snapping.js':'snapping.js','/designer.css':'designer.css','/ux-minimal.css':'ux-minimal.css','/ux-designer.css':'ux-designer.css','/generation.css':'generation.css','/designer.js':'designer.js','/distribution.js':'distribution.js','/onboarding.js':'onboarding.js','/onboarding.css':'onboarding.css','/vendor/svg-edit/studio-core.js':'vendor/svg-edit/studio-core.js','/':'index.html','/app.js':'app.js','/ux-minimal.js':'ux-minimal.js','/ux-designer.js':'ux-designer.js','/hwpx-export.js':'hwpx-export.js','/layers.js':'layers.js','/vectors.js':'vectors.js','/style.css':'style.css','/teacher-theme.css':'teacher-theme.css','/teacher-ui.js':'teacher-ui.js','/fonts/pretendard-gov.woff2':'../fonts/pretendard-gov/PretendardGOVVariable.woff2'}
            static.update({path:path.lstrip('/') for path in ('/favicon.ico','/favicon-192.png','/icons/studio.svg','/icons/testcraft.svg','/icons/icon-16.png','/icons/icon-24.png','/icons/icon-32.png','/icons/icon-48.png','/icons/icon-64.png','/icons/icon-128.png','/icons/icon-180.png','/icons/icon-192.png','/icons/icon-256.png','/icons/icon-512.png','/site.webmanifest')})
            if p not in static: self.send({'error':'페이지 없음'},404); return
            f=core.ROOT/'app/static'/static[p]
            content_types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.woff2':'font/woff2','.svg':'image/svg+xml','.png':'image/png','.ico':'image/x-icon','.webmanifest':'application/manifest+json; charset=utf-8'}
            content=f.read_bytes()
            if p=='/':
                port=getattr(getattr(self,'server',None),'server_address',('127.0.0.1',8765))[1]
                content=content.replace(b'http://127.0.0.1:8765/icons/',f'http://127.0.0.1:{port}/icons/'.encode())
            if p=='/' and q.get('ux',['new'])[0]=='old':
                page=content.decode('utf-8')
                page=page.replace('<link rel="stylesheet" href="/ux-minimal.css"><link rel="stylesheet" href="/ux-designer.css">','')
                page=page.replace('<script src="/ux-minimal.js" defer></script><script src="/ux-designer.js" defer></script>','')
                content=page.encode('utf-8')
            self.send(content,content_type=content_types[f.suffix])
        except Exception as e: self.send({'error':str(e)},400)

    def do_POST(self):
        try:
            self.check_host()
            if self.headers.get('X-Studio-Token')!=TOKEN: self.send({'error':'앱을 새로고침해 주세요.'},403); return
            size=int(self.headers.get('Content-Length','0'))
            if size>20_000_000: raise ValueError('요청 크기는 20MB 이하여야 합니다.')
            data=json.loads(self.rfile.read(size))
            path=urllib.parse.urlsplit(self.path).path
            if path=='/api/codex/install':
                self.send(codex_setup.install(bool(data.get('repair')))); return
            if path in ('/api/codex/login','/api/codex/login/start'):
                self.send(codex_setup.login_start()); return
            if path in ('/api/codex/cancel','/api/codex/login/cancel'):
                self.send(codex_setup.login_cancel()); return
            if runtime.installed_mode():
                if path=='/api/jobs' and data.get('provider','codex')!='codex':
                    self.send({'error':'설치된 앱은 ChatGPT Codex 로그인으로만 생성 작업을 진행합니다.','code':'codex_required'},403); return
                auth=codex_setup.status()
                if not auth.get('ready'):
                    self.send({'error':auth.get('error') or '유료 ChatGPT 로그인 후 사용할 수 있습니다.',
                               'code':'codex_required','codex':auth},403); return
            if path=='/api/label-preview':
                self.send(labels.render(data.get('kind'),data.get('text'),data.get('size')));return
            if path=='/api/math-preview':
                from .mathtext import math_segments
                source=data.get('text','')
                if not isinstance(source,str) or len(source)>50000: raise ValueError('미리보기 글은 50,000자 이하여야 합니다.')
                size=data.get('size',18)
                segments=[]
                for kind,value in math_segments(source):
                    if kind=='math':
                        rendered=labels.render('math',value,size)
                        segments.append({'type':'math','text':value,'url':rendered['url'],'width':rendered['width'],'height':rendered['height']})
                    else: segments.append({'type':'text','text':value})
                self.send({'segments':segments});return
            with core.LOCK:
                eid=data.get('exam_id')
                if eid and eid in ACTIVE and path!='/api/cancel': raise ValueError('생성 작업 중에는 편집할 수 없습니다. 완료 후 다시 시도해 주세요.')
                duplicate_exam=None
                if path=='/api/duplicate-card':
                    duplicate_exam=core.read_exam(eid)
                    request_id=data.get('request_id')
                    if request_id is not None:
                        if not isinstance(request_id,str) or not request_id.strip() or len(request_id)>200:
                            raise ValueError('복제 요청 ID는 1~200자의 문자열이어야 합니다.')
                        request_id=request_id.strip()
                        prior=next((item for item in duplicate_exam.get('duplicate_requests',[])
                                    if item.get('request_id')==request_id),None)
                        if prior:
                            if prior.get('source_card_id')!=data.get('card_id'):
                                raise ValueError('이미 다른 문항 복제에 사용한 요청 ID입니다.')
                            if not any(card.get('id')==prior.get('card_id') for card in duplicate_exam['cards']):
                                raise ValueError('이 복제 요청의 문항이 현재 시험에서 삭제되었습니다.')
                            self.send({'exam':exam_for_client(duplicate_exam),'card_id':prior['card_id']}); return
                if eid and path!='/api/cancel' and (duplicate_exam or core.read_exam(eid))['revision']!=data.get('revision'):
                    latest=duplicate_exam or core.read_exam(eid)
                    self.send({'error':'다른 화면에서 변경된 내용이 있습니다. 최신본과 내 초안을 비교해 주세요.','code':'revision_conflict','latest':latest},409); return
                if path=='/api/create':
                    title=str(data.get('title','')).strip()
                    if not title or len(title)>200: raise ValueError('시험 제목을 1~200자로 입력해 주세요.')
                    mode=core.normalize_authoring_mode(data.get('authoring_mode','legacy'))
                    exam={'id':core.uid(),'title':title,'subject':str(data.get('subject','')),'cards':[core.blank_card(authoring_mode=mode)],'revision':0,'created':core.now(),'updated':core.now(),'exports':[]}
                    if data.get('legacy'):
                        allowed={str(f.relative_to(core.ROOT)).replace('\\','/'):f for f in (core.ROOT/'exams').glob('*/02_card/*.xlsx')}
                        if data['legacy'] not in allowed: raise ValueError('기존 회차 경로 오류')
                        exam['cards']=core.import_cards(allowed[data['legacy']].read_bytes())
                        exam['source']=data['legacy']
                    if data.get('xlsx'): exam['cards']=core.import_cards(base64.b64decode(data['xlsx'],validate=True))
                    core.check_subject(exam['subject'],exam['cards'])
                    if all(c['difficulty'] in ('상','중','하') for c in exam['cards']) and abs(sum(float(c['points'] or 0) for c in exam['cards'])-100)>.001:
                        core.allocate_points(exam['cards'])
                    self.send(exam_for_client(core.save_exam(exam))); return
                if path=='/api/duplicate-card':
                    exam=duplicate_exam or core.read_exam(eid)
                    if len(exam['cards'])>=100: raise ValueError('문항 수는 1~100개여야 합니다.')
                    source_id=data.get('card_id')
                    if not isinstance(source_id,str) or not re.fullmatch('[a-f0-9]{16}',source_id):
                        raise ValueError('복제할 문항 ID가 올바르지 않습니다.')
                    source_index=next((i for i,card in enumerate(exam['cards']) if card.get('id')==source_id),None)
                    if source_index is None: raise ValueError('복제할 문항을 찾을 수 없습니다.')
                    created_paths=[]
                    try:
                        clone=duplicate_card_record(eid,exam,source_index,created_paths)
                        cards=copy.deepcopy(exam['cards'])
                        cards.insert(source_index+1,clone)
                        for index,card in enumerate(cards,1): card['no']=index
                        exam['cards']=cards
                        exam['card_approval']=None
                        if data.get('request_id') is not None:
                            request_id=data['request_id'].strip()
                            ledger=list(exam.get('duplicate_requests') or [])
                            ledger.append({'request_id':request_id,'source_card_id':source_id,'card_id':clone['id']})
                            exam['duplicate_requests']=ledger[-DUPLICATE_REQUESTS_MAX:]
                        saved=core.save_exam(exam)
                    except Exception:
                        remove_created_assets(created_paths)
                        raise
                    self.send({'exam':exam_for_client(saved),'card_id':clone['id']}); return
                if path=='/api/save':
                    exam=core.read_exam(eid)
                    if exam['revision']!=data.get('revision'):
                        self.send({'error':'다른 화면에서 변경된 내용이 있습니다. 최신본과 내 초안을 비교해 주세요.','code':'revision_conflict','latest':exam},409); return
                    if not 1<=len(data['cards'])<=100: raise ValueError('문항 수는 1~100개여야 합니다.')
                    old={c['id']:c for c in exam['cards']}; cards=[]
                    for i,raw in enumerate(data['cards'],1):
                        c=core.normalize(raw,i); prev=old.get(c['id'])
                        preserve_authoring_metadata(c,raw,prev or {})
                        preserve_material_server_state(c,prev or {})
                        for block in core.material_blocks(c):
                            if block.get('kind')!='image': continue
                            projected,mid=core.material_projection(c,block['id'],require_image=True)
                            save_scene(eid,projected)
                            core.sync_material_projection(c,projected,mid)
                        if not prev or core.content_hash(c)!=core.content_hash(prev): c['review_approved']=False
                        cards.append(c)
                    if len({c['id'] for c in cards})!=len(cards): raise ValueError('문항 ID 중복')
                    title=str(data.get('title',exam['title'])).strip()
                    if not title or len(title)>200: raise ValueError('제목 오류')
                    subject=str(data.get('subject',exam['subject']))
                    core.check_subject(subject,cards)
                    if subject!=exam['subject']: exam['card_approval']=None
                    exam.update(cards=cards,title=title,subject=subject)
                    self.send(core.save_exam(exam)); return
                if path=='/api/delete': self.send(delete_exam(eid,data.get('confirm_title'))); return
                if path=='/api/vectorize':
                    exam=core.read_exam(eid);parent=next(c for c in exam['cards'] if c['id']==data['card_id']);card,mid=image_material_targets(parent,data.get('material_id'))[0];im=card.get('image')
                    if not im:raise ValueError('먼저 그림을 생성하거나 업로드하세요.')
                    if card.get('image_scene') is not None:raise ValueError('이미 객체로 변환된 그림입니다.')
                    if hashlib.sha256(asset_path(eid,im['file']).read_bytes()).hexdigest()!=im['sha256']:raise ValueError('원본 그림 파일이 변경되었습니다.')
                    card['image_scene']=vectors.from_svg(asset_path(eid,im['svg']).read_text(encoding='utf-8'),im['sha256']) if im.get('svg') else vectors.from_raster(asset_path(eid,im['file']),im['sha256'],data.get('threshold',190))
                    save_scene(eid,card);core.sync_material_projection(parent,card,mid)
                    self.send(core.save_exam(exam));return
                if path=='/api/confirm-image-plan':
                    exam=core.read_exam(eid)
                    if not core.cards_approved(exam): raise ValueError('문항카드 전체 승인 후 그림 제작 범위를 확인해 주세요.')
                    parent=next(c for c in exam['cards'] if c['id']==data['card_id']);card,mid=image_material_targets(parent,data.get('material_id'))[0]
                    errors=core.image_plan_errors(card)
                    if card['data_kind']!='image' or errors: raise ValueError('그림 제작 범위를 확인해 주세요. '+' / '.join(errors))
                    card['image_plan_approval']={'context':core.image_plan_context(card),'mode':card['image_mode'],'confirmed_at':core.now()}
                    core.sync_material_projection(parent,card,mid)
                    self.send(core.save_exam(exam)); return
                if path=='/api/jobs': self.send(launch_job(eid,data)); return
                if path=='/api/score-preview':
                    exam=core.read_exam(eid); before={c['id']:c['points'] for c in exam['cards']}; cards=core.allocate_points(copy.deepcopy(exam['cards']))
                    self.send({'points':[{'card_id':c['id'],'no':c['no'],'difficulty':c['difficulty'],'before':before.get(c['id']),'after':c['points']} for c in cards],
                               'total':round(sum(float(c['points'] or 0) for c in cards),3)}); return
                if path=='/api/allocate':
                    exam=core.read_exam(eid)
                    exam['cards']=core.allocate_points(exam['cards'])
                    self.send(core.save_exam(exam)); return
                if path=='/api/approve-cards':
                    exam=core.read_exam(eid)
                    report=core.validate(exam,'cards')
                    if not report['ready']: raise ValueError('문항카드 승인 전 확인: '+' / '.join(report['errors'][:8]))
                    exam['card_approval']={'digest':core.cards_digest(exam['cards']),'approved_at':core.now()}
                    self.send(core.save_exam(exam)); return
                if path=='/api/cancel':
                    event=CANCEL.get(data['job_id'])
                    if event: event.set()
                    self.send({'ok':True}); return
                if path in ('/api/image','/api/approve','/api/verify'):
                    exam=core.read_exam(eid); parent=next(c for c in exam['cards'] if c['id']==data['card_id'])
                    if path=='/api/image':
                        if not core.cards_approved(exam): raise ValueError('문항카드를 먼저 전체 승인해 주세요. 승인 후 실제 그림을 적용합니다.')
                        card,mid=image_material_targets(parent,data.get('material_id'))[0]
                        if card['data_kind']!='image': raise ValueError('문항카드에서 자료 종류를 그림으로 설정하고 승인해 주세요.')
                        if not core.image_plan_confirmed(card): raise ValueError('그림 유형과 제작 범위를 먼저 확인해 주세요.')
                        raw=base64.b64decode(data.get('image',''),validate=True)
                        if data.get('library'):
                            name=data['library']
                            if Path(name).name!=name or '/' in name or '\\' in name or not name.endswith('.png'): raise ValueError('라이브러리 파일 오류')
                            raw=(core.ROOT/'reference/image-workflow/png/hml_text_2_5x_pass'/name).read_bytes()
                        card['image']=make_image(eid,card,raw)
                        core.sync_material_projection(parent,card,mid)
                    elif path=='/api/approve':
                        if data.get('kind')=='image':
                            card,mid=image_material_targets(parent,data.get('material_id'))[0]
                            if not data.get('approved'):
                                if card.get('image'):
                                    card['image']['approved']=False
                                    card['image'].pop('approval_override',None)
                            else:
                                if not core.cards_approved(exam): raise ValueError('문항카드 전체 승인이 필요합니다.')
                                if not core.image_plan_confirmed(card): raise ValueError('그림 유형과 제작 범위를 먼저 확인해 주세요.')
                                if not card['image'] or card['image'].get('context')!=core.image_context(card): raise ValueError('현재 문항의 그림을 먼저 생성해 주세요.')
                                image_approval_preflight(eid,card)
                                check_results=core.image_check_results(card['image'].get('checks') or [])
                                failures=[item for item in check_results if not item['ok']]
                                override_digest=core.image_validation_digest(card)
                                raw_override=data.get('override')
                                supplied=raw_override if isinstance(raw_override,dict) else {}
                                if failures and (supplied.get('kind')!='image' or supplied.get('validation_digest')!=override_digest):
                                    self.send({'error':'그림 제약 검사에서 불일치가 발견됐습니다. 확인 후 그래도 승인할 수 있습니다.',
                                               'code':'approval_discrepancy','details':{'kind':'image','card_id':parent['id'],'material_id':mid,'no':parent['no'],
                                               'content_digest':core.content_hash(card),'context_digest':core.image_context(card),
                                               'image_digest':core.image_final_digest(card),'validation_digest':override_digest,
                                               'checks':check_results,'override_allowed':True,
                                               'override_rejected':bool(raw_override)}},409);return
                                finalize_image(eid,card,override_digest if failures else None)
                            core.sync_material_projection(parent,card,mid)
                        else:
                            card=parent
                            approved=bool(data.get('approved'))
                            if not approved:
                                card['review_approved']=False
                                card['calculation_override']=None
                            elif card.get('calculation'):
                                input_errors=core.calculation_input_errors(card)
                                if input_errors:
                                    self.send({'error':'계산 확인에 필요한 입력을 먼저 채워 주세요.','code':'approval_blocked',
                                               'details':{'kind':'calculation','card_id':card['id'],'no':card['no'],
                                               'field':'checks','blockers':input_errors,'override_allowed':False}},400);return
                                check_results=core.verify_checks(card['checks'])
                                failures=[item for item in check_results if not item['ok']]
                                override_digest=core.calculation_validation_digest(card)
                                raw_override=data.get('override')
                                supplied=raw_override if isinstance(raw_override,dict) else {}
                                if failures and (supplied.get('kind')!='calculation' or supplied.get('validation_digest')!=override_digest):
                                    self.send({'error':'계산식에서 불일치가 발견됐습니다. 확인 후 그래도 승인할 수 있습니다.',
                                               'code':'approval_discrepancy','details':{'kind':'calculation','card_id':card['id'],'no':card['no'],
                                               'content_digest':core.content_hash(card),'validation_digest':override_digest,
                                               'checks':check_results,'override_allowed':True,'override_rejected':bool(raw_override)}},409);return
                                if failures:
                                    card['calculation_override']={'content_digest':core.content_hash(card),
                                        'validation_digest':override_digest,'approved_at':core.now()}
                                else: card['calculation_override']=None
                                card['review_approved']=True
                            else:
                                card['calculation_override']=None
                                card['review_approved']=True
                    else:
                        card=parent
                        results=core.verify_checks(card['checks'])
                        self.send({'checks':results,'calculation':{
                            'required':bool(card.get('calculation')),
                            'blockers':core.calculation_input_errors(card),
                            'content_digest':core.content_hash(card),
                            'validation_digest':core.calculation_validation_digest(card),
                            'override_allowed':bool(card.get('calculation') and not core.calculation_input_errors(card) and any(not item['ok'] for item in results)),
                            'override_active':core.calculation_override_active(card),
                        }}); return
                    self.send(core.save_exam(exam)); return
                if path=='/api/export':
                    exam=core.read_exam(eid); bundle=export_exam(exam)
                    exam['exports'].append(bundle); self.send(core.save_exam(exam)); return
                if path=='/api/recalculate':
                    exam=core.read_exam(eid); rid=data['export_id']
                    recalculate_export(exam,rid)
                    self.send(core.save_exam(exam)); return
                raise ValueError('알 수 없는 요청')
        except Exception as e:
            self.send({'error':str(e)},400)

class StudioHTTPServer(ThreadingHTTPServer):
    # Startup loads several JS/CSS files at once; leave room for a local burst
    # instead of the stdlib TCPServer default backlog of five connections.
    request_queue_size = 64

def serve(port=8765):
    core.DATA.mkdir(parents=True,exist_ok=True)
    server=StudioHTTPServer(('127.0.0.1',port),Handler)
    print(f'TestCraft: http://127.0.0.1:{port}',flush=True)
    server.serve_forever()
