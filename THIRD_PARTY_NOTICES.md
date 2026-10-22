# 배포 구성 요소와 소스

문항 스튜디오의 자체 소스는 GNU AGPL-3.0으로 배포합니다. 다른 구성 요소의 라이선스를 변경하지 않습니다. 설치 파일에는 필요한 라이선스 원문과 배포 버전·체크섬을 포함합니다.

| 구성 요소 | 라이선스 | 대응 소스와 안내 |
|---|---|---|
| CPython 3.13.17 | PSF 및 포함 구성 요소의 라이선스 | https://www.python.org/downloads/release/python-31317/ |
| Node.js 24.22.1 | MIT 및 포함 구성 요소의 라이선스 | https://nodejs.org/download/release/v24.22.1/ |
| OpenAI Codex CLI 0.163.0 | Apache-2.0 및 포함 구성 요소의 라이선스 | https://github.com/openai/codex/tree/rust-v0.163.0 |
| Sharp 0.34.x / libvips | Apache-2.0 / LGPL-2.1 및 포함 라이브러리 | https://github.com/lovell/sharp , https://github.com/libvips/libvips |
| PyMuPDF 1.28.2 / MuPDF | GNU AGPL-3.0 | https://github.com/pymupdf/PyMuPDF/tree/1.28.2 , https://mupdf.com/ |
| pyhwpx 1.7.2 | MIT | https://github.com/martiniifun/pyhwpx |
| SVG-Edit 발췌 코드 | MIT | app/static/vendor/svg-edit/LICENSE-MIT.txt 및 REVISION.txt |
| Latin Modern Math | GUST Font License | app/fonts/latinmodern-math-1959/doc/GUST-FONT-LICENSE.txt |
| Pretendard GOV | SIL OFL-1.1 | app/fonts/pretendard-gov/LICENSE.txt |

Python 의존성의 정확한 버전은 `packaging/requirements-windows.lock`, Node 의존성은 `package-lock.json`, 원본 실행 환경의 URL·체크섬은 `packaging/runtime-inputs.json`에 기록합니다. 해당 버전의 소스 배포본은 PyPI의 각 패키지 버전 페이지와 각 공식 저장소에서 받을 수 있습니다. 설치된 각 Python 패키지의 `.dist-info`와 `notices/python`에도 라이선스와 메타데이터를 보존합니다.

한컴오피스 한글 및 신명 중명조 HFT 글꼴은 포함하지 않습니다. 해당 기능은 사용자가 적법하게 설치한 한글을 통해 실행됩니다. Codex 계정·구독·인증 정보 또한 포함하지 않습니다.
