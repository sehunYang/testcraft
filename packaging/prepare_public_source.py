"""Create/update a publication tree from an explicit source allowlist.

Never copies exams, lesson records, historical statistics, caches or credentials.
The working teacher project stays unchanged. Run before initializing the public repo.
"""
import argparse
import re
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INSTRUCTIONS=(
    '과학수업-피드백-문항출제-에이전트-지침.md',
    '문항-문안-다듬기-지침.md','참조자료-제반사항.md',
    '과학-선화-생성-지침.md','HWPML-문항지-생성-지침.md',
    '통합-앱-사용법.md','자료-디자인-오픈소스.md',
    '영상-제작-운영.md',
)
TOOLS=('gen.py','metrics.py','hwp_equation.py','수식크기_재계산.py','build_brand_assets.cjs','build_site.py','capture_site_demo.cjs',
       'media_requirements.txt','media-script.json','serve_media_studio.py','capture_media.cjs','build_media_audio.py','render_media.py','verify_media.py')
def copy(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,destination)
def prepare(destination):
    destination=destination.resolve()
    if destination==ROOT or ROOT in destination.parents and destination.name in {'app','exams','reference','instructions','tools','templates'}:
        raise ValueError('Choose a separate publication directory.')
    destination.mkdir(parents=True,exist_ok=True)
    for relative in ('app','packaging','docs'):
        for source in (ROOT/relative).rglob('*'):
            if not source.is_file() or '__pycache__' in source.parts or source.suffix in {'.pyc','.pyo','.log'}:continue
            copy(source,destination/source.relative_to(ROOT))
    for source in (ROOT/'tests').glob('*.py'):copy(source,destination/'tests'/source.name)
    for name in ('browser_branding.cjs','browser_hwpx_export.cjs','browser_site.cjs','browser_tutorials.cjs','browser_media.cjs'):
        copy(ROOT/'tests'/name,destination/'tests'/name)
    for name in TOOLS:copy(ROOT/'tools'/name,destination/'tools'/name)
    for source in (ROOT/'templates').iterdir():
        if source.is_file() and source.suffix in {'.xlsx','.hml','.md'}:
            target=destination/'templates'/source.name
            copy(source,target)
            if source.name=='평가문항-템플릿.md':
                text=target.read_text(encoding='utf-8')
                for label in ('총 피험자 수','직전 평가 평균','직전 평가 표준편차','인지 발달 단계'):
                    text=re.sub(r'^\| '+re.escape(label)+r' \|.*$', '| '+label+' | 사용자 입력 | |',text,flags=re.M)
                target.write_text(text,encoding='utf-8')
    for name in INSTRUCTIONS:
        text=(ROOT/'instructions'/name).read_text(encoding='utf-8')
        if name=='참조자료-제반사항.md':
            # The source section contains a real class's assessment statistics.
            start=text.index('## 1. 학생 수준')
            following=re.search(r'^## 2\.',text[start:],re.M)
            if not following:raise ValueError('Student-level section boundary changed; review before publishing.')
            text=text[:start]+'## 1. 학생 수준\n\n공개 배포본에는 특정 학교·학급의 학생 수, 성적, 평가 이력을 포함하지 않습니다. 사용자가 제공하지 않은 집단 수준이나 목표 점수를 추정하여 사실처럼 쓰지 않습니다.\n\n'+text[start+following.start():]
        target=destination/'instructions'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
    (destination/'instructions/00-작업-흐름.md').write_text('# TestCraft 작업 흐름\n\nCodex 연결 → 설계 → 검토·배점·전체 승인 → 자료 그림 → 출력 순서로 진행합니다. 자료 그림의 실제 제작은 전체 문항카드 승인 후 진행합니다.\n\n자세한 사용 방법은 [통합-앱-사용법.md](통합-앱-사용법.md), 설치와 빌드는 저장소 README를 참고하세요.\n',encoding='utf-8')
    for name in ('package.json','package-lock.json','requirements.txt','run_studio.py','LICENSE','THIRD_PARTY_NOTICES.md'):
        if (ROOT/name).is_file():copy(ROOT/name,destination/name)
    copy(ROOT/'packaging/public-README.md',destination/'README.md')
    (destination/'.gitignore').write_text('.runtime/\n.runtime*/\n.venv/\n__pycache__/\n*.py[cod]\nnode_modules/\ndist/\nexams/\nlessons/\nreference/\n.env*\nauth.json\n*.log\n',encoding='utf-8')
    workflow=ROOT/'packaging/release-workflow.yml'
    if workflow.is_file():copy(workflow,destination/'.github/workflows/release.yml')
    workflow=ROOT/'packaging/test-workflow.yml'
    if workflow.is_file():copy(workflow,destination/'.github/workflows/test.yml')
    workflow=ROOT/'packaging/pages-workflow.yml'
    if workflow.is_file():copy(workflow,destination/'.github/workflows/pages.yml')
    # Private past exams are deliberately absent from the public repository.
    test=destination/'tests/test_workflow.py'
    text=test.read_text(encoding='utf-8')
    text=text.replace("source=next((core.ROOT/'exams').glob('*/02_card/*.xlsx'))", "source=next((core.ROOT/'exams').glob('*/02_card/*.xlsx'),None)\n        if source is None:self.skipTest('Private past exams are not distributed.')")
    test.write_text(text,encoding='utf-8')
    prohibited={'exams','lessons','reference','.codex','.aws','.runtime','node_modules','__pycache__'}
    for path in destination.rglob('*'):
        relative=path.relative_to(destination)
        if '.git' in relative.parts:continue
        if any(part in prohibited for part in relative.parts):raise ValueError('Prohibited publication path: '+str(relative))
    print(str(destination))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    prepare(parser.parse_args().destination)
