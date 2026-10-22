# -*- coding: utf-8 -*-
"""
수식 크기 재계산 스크립트  (pyhwpx / 한글 COM)

문항지 .hml 을 한글로 열어 모든 수식 개체의 속성을 한글에게 다시 넘겨줍니다.
그러면 한글이 수식을 다시 그리면서 폭·높이·기준선을 스스로 계산합니다.
→ 겹침·잘림·여백이 한 번에 사라집니다.

사용법
  1) 한글을 닫아 둡니다.
  2) python tools/수식크기_재계산.py            (가장 최근 회차의 03_paper/문항지.hml)
     python tools/수식크기_재계산.py 회차폴더이름
     python tools/수식크기_재계산.py 입력.hml 출력.hwp
"""
import os, sys, time, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _latest_exam():
    base = os.path.join(ROOT, 'exams')
    c = [os.path.join(base, x) for x in os.listdir(base)
         if os.path.isdir(os.path.join(base, x)) and not x.startswith('_')]
    if not c: sys.exit("exams/ 아래에 회차 폴더가 없습니다.")
    return max(c, key=os.path.getmtime)

_a = [v for v in sys.argv[1:] if not v.startswith('-')]
if len(_a) >= 2:
    IN_PATH, OUT_PATH = _a[0], _a[1]
else:
    _exam = os.path.join(ROOT, 'exams', _a[0]) if _a else _latest_exam()
    IN_PATH  = os.path.join(_exam, '03_paper', '문항지.hml')
    OUT_PATH = os.path.join(_exam, '03_paper', '문항지(크기재계산).hwp')
print("  입력:", IN_PATH)
print("  출력:", OUT_PATH)

try:
    from pyhwpx import Hwp
except ImportError:
    sys.exit("pyhwpx 가 없습니다.  pip install pyhwpx  후 다시 실행하세요.")

def main():
    if not os.path.exists(IN_PATH):
        sys.exit(f"파일을 찾을 수 없습니다: {IN_PATH}")

    hwp = Hwp()
    hwp.open(IN_PATH)
    print("문서를 열었습니다:", os.path.basename(IN_PATH))

    total = touched = failed = 0
    ctrl = hwp.HeadCtrl
    while ctrl:
        nxt = ctrl.Next                      # 속성 변경 전에 다음 개체를 잡아 둔다
        if ctrl.CtrlID == "eqed":            # eqed = 수식 개체
            total += 1
            try:
                pset = ctrl.Properties
                # 수식 문자열을 자기 자신으로 다시 써 넣으면 한글이 수식을 다시 그린다
                for key in ("String", "EqScript", "Script"):
                    try:
                        val = pset.Item(key)
                        if val is not None:
                            pset.SetItem(key, val)
                            break
                    except Exception:
                        continue
                ctrl.Properties = pset       # ← 이 대입이 재계산을 일으킨다
                touched += 1
            except Exception as e:
                failed += 1
                if failed <= 3: print("  건너뜀:", e)
        ctrl = nxt

    print(f"수식 {total}개 중 {touched}개 재계산, {failed}개 실패")

    hwp.HAction.Run("MoveDocEnd")
    time.sleep(0.3)
    hwp.save_as(OUT_PATH)
    print("저장했습니다:", OUT_PATH)
    print("\n한글에서 열어 21·22·23·24번의 수식을 확인하십시오.")

if __name__ == "__main__":
    main()
