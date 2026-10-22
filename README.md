# 문항 스튜디오 · Question Studio

교사가 성취기준과 문항 의도를 설계하고, AI 초안을 검토한 뒤 자료 그림과 시험지·해설을 만드는 Windows 로컬 앱입니다.

## 설치

1. [최신 릴리스](https://github.com/sehunYang/question-studio/releases/latest)에서 `QuestionStudio-1.0.0-windows-x64-setup.exe`를 받습니다.
2. 설치 후 시작 메뉴의 **Question Studio**를 실행합니다. 관리자 권한은 필요하지 않습니다.
3. 첫 화면에서 내장 Codex CLI 확인을 기다리고, **Codex 계정으로 로그인**을 누릅니다. 공식 로그인 페이지에서 Codex를 사용할 수 있는 유료 ChatGPT 계정으로 인증합니다.

Windows 10/11 x64용입니다. Python·Node.js·Codex CLI와 필요한 렌더링 모듈을 포함합니다. API 키를 입력할 필요가 없습니다. 서비스 계정과 구독은 별도로 필요하며 설치 파일에 인증 정보가 포함되지 않습니다.

한컴오피스 한글이 설치되어 있으면 신명 중명조 한글 글씨 레이어와 HWP 변환·수식 크기 재계산 기능을 사용할 수 있습니다. 한글 프로그램과 해당 글꼴은 재배포하지 않습니다. Latin Modern Math와 Pretendard GOV는 해당 라이선스와 함께 포함합니다.

## 출제 흐름

**설계 → 검토 → 그림 → 출력** 순서로 진행합니다.

- AI 초안 또는 직접 작성 선택, 문항 복제·삭제·순서 변경
- 단일 정답형·합답형·불완전 문장형·짝짓기형과 과목별 성취기준
- 유형·난이도·정답·성취기준 분포 현황
- 문항별 복합 자료와 (가)·(나) 그림 구성
- 문항 검토·배점·전체 승인 후 실제 그림 제작
- strict·mixed·flexible 그림 프롬프트와 독립 글씨 레이어
- SVG 객체 편집·회전·스냅, 글씨 추가·이동·후편집
- 학생용·교사용 HML, 해설 Markdown, 문항카드 XLSX, ZIP 출력

시험과 그림은 내 컴퓨터의 `%LOCALAPPDATA%\QuestionStudio`에 저장됩니다. 업데이트와 앱 제거 시 이 폴더를 삭제하지 않습니다. AI 생성 시 선택한 문항 내용은 로그인한 Codex 서비스로 전달됩니다. 생성 결과와 계산·그림은 교사가 검토하고 승인합니다.

## 소스 실행과 빌드

```powershell
python -m pip install -r requirements.txt
npm ci
python run_studio.py
```

개발 모드는 기존 Codex/Claude 연결도 지원하며, 설치 배포본은 내장 Codex와 유료 ChatGPT 로그인 흐름을 사용합니다. 설치 모드를 소스에서 점검하려면 `QUESTION_STUDIO_INSTALLED=1`을 설정합니다. 자세한 재현 빌드는 [packaging/README.md](packaging/README.md)를 참고하세요.

```powershell
New-Item -ItemType Directory -Force .runtime
python -m unittest discover -s tests -p "test_*.py"
```

공개 소스에는 기존 시험·학생 성적·학급 통계·인증 파일을 포함하지 않습니다. 학교 HML 및 빈 문항카드 템플릿과 교육과정 성취기준은 앱 동작에 필요한 재사용 자산입니다.

## 라이선스

프로젝트는 **GNU AGPL-3.0**으로 공개합니다. 포함된 다른 구성 요소는 각각의 라이선스를 유지합니다. [LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 및 설치 폴더의 `notices`를 참고하세요. OpenAI 또는 한컴의 공식 제품이 아닙니다.
