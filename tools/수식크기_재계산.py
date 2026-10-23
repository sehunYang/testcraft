# -*- coding: utf-8 -*-
"""Recalculate HML equations in Hancom and save HWP/HWPX output.

Legacy usage remains supported::

    python tools/수식크기_재계산.py input.hml output.hwp

The app uses the batch mode to convert the student and teacher papers in one
isolated helper process::

    python tools/수식크기_재계산.py --batch student.hml student.hwpx teacher.hml teacher.hwpx

Argument parsing and exam discovery happen only in ``main`` so importing this
module has no command-line side effects.
"""
import os
from pathlib import Path
import sys
import site

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PACKAGES = ROOT / '.runtime' / 'packages'
if RUNTIME_PACKAGES.is_dir():
    site.addsitedir(str(RUNTIME_PACKAGES))
    sys.path.insert(0, str(RUNTIME_PACKAGES))
_PYWIN32_DLL_DIRECTORY = None
PYWIN32_DLLS = RUNTIME_PACKAGES / 'pywin32_system32'
if PYWIN32_DLLS.is_dir() and hasattr(os, 'add_dll_directory'):
    _PYWIN32_DLL_DIRECTORY = os.add_dll_directory(str(PYWIN32_DLLS))
PROG_ID = 'HWPFrame.HwpObject'


def _new_isolated_hwp():
    """Create a fresh Hancom COM server without consulting or attaching to ROT."""
    from pyhwpx import Hwp
    import win32com.client as win32

    # pyhwpx's ``new=True`` skips its own ROT scan, but calls EnsureDispatch
    # with a ProgID. Constructing the COM object via DispatchEx first makes
    # new-server activation explicit; EnsureDispatch then only wraps that
    # already-created object with pywin32's generated interface.
    ensure_dispatch = win32.gencache.EnsureDispatch
    created_objects = []

    def ensure_fresh(target, bForDemand=1):
        if target == PROG_ID:
            target = win32.DispatchEx(PROG_ID)
            created_objects.append(target)
        return ensure_dispatch(target, bForDemand=bForDemand)

    win32.gencache.EnsureDispatch = ensure_fresh
    try:
        try:
            return Hwp(new=True, visible=False)
        except BaseException:
            # Hwp.__init__ can fail after DispatchEx has already started a
            # private server. Close only objects created by this helper.
            for obj in reversed(created_objects):
                try: obj.Quit()
                except Exception: pass
            raise
    finally:
        win32.gencache.EnsureDispatch = ensure_dispatch


def convert_one(input_path, output_path, output_format=None):
    """Open one HML, recalculate every equation, and explicitly SaveAs."""
    source = Path(input_path).resolve()
    destination = Path(output_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f'파일을 찾을 수 없습니다: {source}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fmt = output_format or ('HWPX' if destination.suffix.lower() == '.hwpx' else 'HWP')
    if fmt not in ('HWP', 'HWPX'):
        raise ValueError(f'지원하지 않는 출력 형식입니다: {fmt}')

    hwp = None
    error = None
    total = touched = 0
    try:
        hwp = _new_isolated_hwp()
        if not hwp.open(str(source)):
            raise RuntimeError(f'한글이 입력 문서를 열지 못했습니다: {source.name}')
        print(f'문서를 열었습니다: {source.name}', flush=True)

        ctrl = hwp.HeadCtrl
        while ctrl:
            nxt = ctrl.Next  # 다음 컨트롤을 속성 갱신 전에 보관한다.
            if ctrl.CtrlID == 'eqed':
                total += 1
                pset = ctrl.Properties
                recalculated = False
                property_errors = []
                for key in ('String', 'EqScript', 'Script'):
                    try:
                        value = pset.Item(key)
                        if value is None:
                            continue
                        pset.SetItem(key, value)
                        ctrl.Properties = pset
                        recalculated = True
                        break
                    except Exception as exc:
                        property_errors.append(f'{key}: {exc}')
                if not recalculated:
                    detail = '; '.join(property_errors[-3:]) or '수식 속성을 읽을 수 없습니다.'
                    raise RuntimeError(f'{source.name}의 {total}번째 수식 재계산 실패: {detail}')
                touched += 1
            ctrl = nxt

        print(f'수식 {total}개 중 {touched}개 재계산', flush=True)
        move_result = hwp.HAction.Run('MoveDocEnd')
        if move_result is False:
            raise RuntimeError('문서 끝으로 이동하지 못했습니다.')
        save_result = hwp.save_as(str(destination), format=fmt, arg='lock:false;backup:false')
        if not save_result:
            raise RuntimeError(f'{fmt} 저장에 실패했습니다: {destination.name}')
        if not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError(f'{fmt} 저장 결과 파일이 없거나 비어 있습니다: {destination.name}')
        print(f'{fmt} 저장 완료: {destination.name}', flush=True)
    except BaseException as exc:
        error = exc
    finally:
        if hwp is not None:
            try:
                hwp.clear()
            except Exception as exc:
                if error is None:
                    error = RuntimeError(f'한글 문서를 정리하지 못했습니다: {exc}')
            try:
                hwp.quit(save=False)
            except Exception as exc:
                if error is None:
                    error = RuntimeError(f'전용 한글 인스턴스를 종료하지 못했습니다: {exc}')
    if error is not None:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise error
    return {'input': str(source), 'output': str(destination), 'format': fmt,
            'equations': total, 'recalculated': touched}


def latest_exam():
    base = ROOT / 'exams'
    candidates = [path for path in base.iterdir()
                  if path.is_dir() and not path.name.startswith('_')]
    if not candidates:
        raise FileNotFoundError('exams/ 아래에 회차 폴더가 없습니다.')
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args and args[0] == '--batch':
            if len(args) < 3 or len(args) % 2 != 1:
                raise ValueError('--batch에는 입력 HML과 출력 HWPX를 쌍으로 지정하세요.')
            for source,destination in zip(args[1::2],args[2::2]):
                print(f'한글 변환 시작: {Path(source).stem}', flush=True)
                convert_one(source,destination,'HWPX')
            return 0

        if len(args) >= 2:
            input_path, output_path = args[:2]
        else:
            exam = ROOT / 'exams' / args[0] if args else latest_exam()
            input_path = exam / '03_paper' / '문항지.hml'
            output_path = exam / '03_paper' / '문항지(크기재계산).hwp'
        print('입력:', input_path)
        print('출력:', output_path)
        convert_one(input_path, output_path)
        return 0
    except Exception as exc:
        print(f'한글 변환 실패: {exc}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
