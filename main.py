# -*- coding: utf-8 -*-
"""토큰화 펀드 배당 검증 — 통합 실행 (한 번 실행으로 수집부터 리포트까지).

    python main.py                 전체 실행. 키·GPU가 없으면 해당 단계는 저장된 결과로 대신한다
    python main.py --no-collect    수집 생략 (저장된 블록체인 데이터로 전처리부터)
    python main.py --no-llm        생성형 AI 단계 생략 (저장된 AI 결과 사용)
    python main.py --dashboard     실행 후 대시보드(Streamlit)까지 띄움
    python main.py --log logs/x.log 실행 기록을 파일로도 남김 (run_daily.ps1이 매일 사용)

단계
  1. 수집      Blockscout·Etherscan API → 검증/data/*.csv           (Etherscan 무료 키 필요: .env)
  2. 전처리    배당·청약·상환 분류, 경과일 정규화, 대사 검사        → 검증/data/clean/
  3. 분석      지급률·요일·자금 흐름, 차트                          → 검증/data/clean/insights.txt, fig_*.png
  4. 문서 대조 투자설명서 인용 검증 대조표                          → 검증/data/clean/doc_vs_chain.json
  5. 생성형 AI 로컬 LLM 조건 추출(5회 다수결) → 규칙 판정 → 리포트  → reports/benji_report.md (Ollama + phi4:14b 필요)
  6. Excel     판정·추출 조건·대조표·실행 요약을 한 파일로          → reports/dividend_check.xlsx
"""
import argparse, json, os, re, subprocess, sys, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V = ROOT / "검증"
CLEAN = V / "data" / "clean"
REPORTS = ROOT / "reports"
PY = sys.executable
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

COLLECT = [("01_collect_buidl.py", "BUIDL 거래 기록"), ("05_collect_buidl_events.py", "BUIDL 소각 사유 이벤트"),
           ("06_collect_benji.py", "BENJI 거래 기록·업그레이드 이력")]


def env_value(key):
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return os.environ.get(key, "")


def ollama_ready():
    """Ollama 서버가 켜져 있고 하네스 모델이 받아져 있는가."""
    import requests
    url = env_value("OLLAMA_URL") or "http://localhost:11434"
    model = env_value("OLLAMA_MODEL") or "phi4:14b"
    try:
        names = [m["name"] for m in requests.get(url + "/api/tags", timeout=3).json().get("models", [])]
    except Exception:
        return False, f"Ollama 서버에 연결할 수 없음 ({url})"
    if model not in names:
        return False, f"Ollama에 모델 {model} 없음 (ollama pull {model})"
    return True, model


class Tee:
    """화면과 로그 파일(UTF-8)에 같이 쓴다. --log 사용 시 (작업 스케줄러 일일 실행용)."""
    def __init__(self, stream, f):
        self.stream, self.f = stream, f

    def write(self, s):
        try:
            self.stream.write(s)
        except Exception:
            pass   # 창 없는 실행 등으로 화면 출력이 안 돼도 로그는 남긴다
        self.f.write(s)

    def flush(self):
        for x in (self.stream, self.f):
            try:
                x.flush()
            except Exception:
                pass


def run(script, label, cwd=ROOT, args=()):
    """스크립트를 실행하고 (성공 여부, 초)를 돌려준다. 출력은 줄 단위로 화면(과 로그)에 옮긴다."""
    print(f"\n── {label} ({Path(script).name})", flush=True)
    t0 = time.time()
    p = subprocess.Popen([PY, str(script), *args], cwd=cwd, env=ENV, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    for line in p.stdout:
        print(line, end="", flush=True)
    rc = p.wait()
    sec = round(time.time() - t0, 1)
    print(f"   → {'완료' if rc == 0 else f'실패 (종료 코드 {rc})'} {sec}초", flush=True)
    return rc == 0, sec


def recon_ok():
    """전처리 대사 검사: 발행·소각 합계 차이가 모두 0인가."""
    t = (CLEAN / "checks.txt").read_text(encoding="utf-8")
    diffs = re.findall(r"대사:.*?차이 ([\d.]+)", t)
    return bool(diffs) and all(float(x) == 0 for x in diffs), len(diffs)


def write_excel(steps, started):
    """판정·추출 조건·사람 대조표·실행 요약을 Excel 한 파일로 (현업 공유용)."""
    import pandas as pd
    from openpyxl.styles import Alignment, Font, PatternFill
    out = REPORTS / "dividend_check.xlsx"
    REPORTS.mkdir(exist_ok=True)
    sheets = {}
    try:
        auto = json.loads((CLEAN / "doc_vs_chain_auto_benji.json").read_text(encoding="utf-8"))
        terms = json.loads((CLEAN / "llm_terms_benji.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        auto, terms = [], None
    if auto:
        sheets["AI 자동 판정"] = pd.DataFrame([{"항목": r["item"], "판정": r["verdict"], "온체인 관측": r["chain"],
                                               "판정 규칙": r["rule"], "문서 원문": r.get("doc_quote")} for r in auto])
    if terms:
        sheets["AI 추출 조건"] = pd.DataFrame([{"항목": k, "값": v["value"], "근거 문장 번호": ", ".join(f"S{i}" for i in v.get("evidence_ids", [])),
                                               "일치율": v["agreement"], "검사 결과": json.dumps(v["statuses"], ensure_ascii=False),
                                               "근거 문장": v.get("evidence")} for k, v in terms["terms"].items()])
    human = json.loads((CLEAN / "doc_vs_chain.json").read_text(encoding="utf-8"))
    sheets["사람 대조표"] = pd.DataFrame([{"펀드": r["fund"], "항목": r["item"], "판정": r["verdict"], "온체인": r["chain"],
                                         "문서 원문": r["doc_quote"], "출처": r["doc_source"], "비고": r["note"]} for r in human])
    summ = [{"항목": "실행 시각", "값": started}]
    for f in ("buidl", "benji"):
        dv = pd.read_csv(CLEAN / f"{f}_dividends.csv")
        summ.append({"항목": f"{f.upper()} 배당 기록", "값": f"{len(dv)}회 ({dv['date_et'].min()} ~ {dv['date_et'].max()})"})
    ok, n = recon_ok()
    summ.append({"항목": "대사 검사 (발행·소각 합계)", "값": f"{'오차 0' if ok else '차이 있음'} ({n}개 항목)"})
    if terms:
        summ.append({"항목": "AI 모델 / 근거 검사", "값": f"{terms['model']} / {terms['verified_rate']} (추출 {terms['runs']}회 {terms['seconds']}초)"})
    for s in steps:
        summ.append({"항목": f"단계: {s['단계']}", "값": f"{s['결과']} {s['초']}초" if s["초"] is not None else s["결과"]})
    sheets = {"실행 요약": pd.DataFrame(summ), **sheets}
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, index=False, sheet_name=name)
            ws = w.sheets[name]
            for c in ws[1]:
                c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="8B1A1A")
            for col in ws.columns:
                width = min(80, max(10, *(len(str(c.value or "")) for c in col)) + 2)
                ws.column_dimensions[col[0].column_letter].width = width
                for c in col[1:]:
                    c.alignment = Alignment(wrap_text=True, vertical="top")
            ws.freeze_panes = "A2"
    return out


def main():
    ap = argparse.ArgumentParser(description="토큰화 펀드 배당 검증 — 수집부터 리포트까지 한 번에 실행")
    ap.add_argument("--no-collect", action="store_true", help="수집 생략, 저장된 블록체인 데이터 사용")
    ap.add_argument("--no-llm", action="store_true", help="생성형 AI 단계 생략, 저장된 AI 결과 사용")
    ap.add_argument("--runs", type=int, default=5, help="AI 조건 추출 반복 횟수 (다수결, 기본 5)")
    ap.add_argument("--dashboard", action="store_true", help="실행 후 대시보드를 띄움")
    ap.add_argument("--log", help="실행 기록을 이 파일에 덧붙여 저장 (UTF-8)")
    a = ap.parse_args()
    if a.log:
        Path(a.log).parent.mkdir(parents=True, exist_ok=True)
        f = open(a.log, "a", encoding="utf-8")
        sys.stdout, sys.stderr = Tee(sys.stdout, f), Tee(sys.stderr, f)

    started = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    print(f"토큰화 펀드 배당 검증 — 통합 실행 시작 {started}")
    steps, t_all = [], time.time()

    # 1. 수집 — 키가 없으면 저장된 데이터로 대신한다 (채점·시연 PC용)
    if a.no_collect:
        steps.append({"단계": "1. 수집", "결과": "생략 (--no-collect, 저장된 데이터 사용)", "초": None})
    elif not env_value("ETHERSCAN_API_KEY"):
        steps.append({"단계": "1. 수집", "결과": "생략 (.env에 ETHERSCAN_API_KEY 없음, 저장된 데이터 사용)", "초": None})
        print("\n── 1. 수집: .env에 Etherscan 키가 없어 저장된 데이터로 진행합니다 (.env.example 참고)")
    else:
        sec_sum = 0
        for script, label in COLLECT:
            ok, sec = run(V / script, f"1. 수집 — {label}", cwd=V)
            sec_sum += sec
            if not ok:
                print("\n수집 실패. 기존 데이터는 그대로 남아 있습니다. 네트워크를 확인하거나 --no-collect로 다시 실행하세요.")
                return 1
        steps.append({"단계": "1. 수집", "결과": "완료", "초": round(sec_sum, 1)})

    # 2~4. 전처리·분석·문서 대조 — CPU 작업, 항상 실행
    for script, name in [("07_preprocess.py", "2. 전처리"), ("08_analyze.py", "3. 분석·차트"), ("10_doc_vs_chain.py", "4. 문서 대조")]:
        ok, sec = run(V / script, name, cwd=V)
        if not ok:
            print(f"\n{name} 실패. 위 오류를 확인하세요.")
            return 1
        steps.append({"단계": name, "결과": "완료", "초": sec})
    ok, n = recon_ok()
    print(f"   대사 검사: {'발행·소각 합계 오차 0' if ok else '차이 있음 — checks.txt 확인'} ({n}개 항목)")
    if not ok:
        print("대사 오차가 있어 AI 단계로 넘어가지 않습니다.")
        return 1

    # 5. 생성형 AI — Ollama·모델이 없으면 저장된 AI 결과를 그대로 쓴다
    if a.no_llm:
        steps.append({"단계": "5. 생성형 AI", "결과": "생략 (--no-llm, 저장된 AI 결과 사용)", "초": None})
    else:
        ready, info = ollama_ready()
        if not ready:
            steps.append({"단계": "5. 생성형 AI", "결과": f"생략 ({info}, 저장된 AI 결과 사용)", "초": None})
            print(f"\n── 5. 생성형 AI: {info} → 저장된 AI 결과로 진행합니다")
        else:
            ok, sec = run(LLM_HARNESS, f"5. 생성형 AI ({info}) — 조건 추출 {a.runs}회·규칙 판정·리포트 작성",
                          args=("all", "--fund", "BENJI", "--runs", str(a.runs)))
            steps.append({"단계": "5. 생성형 AI", "결과": "완료" if ok else "실패 (저장된 AI 결과 유지)", "초": sec})

    # 6. Excel 점검표
    t0 = time.time()
    xlsx = write_excel(steps, started)
    steps.append({"단계": "6. Excel 점검표", "결과": "완료", "초": round(time.time() - t0, 1)})

    # 요약
    total = round(time.time() - t_all, 1)
    print("\n" + "=" * 64)
    print(f"통합 실행 끝 — 전체 {total}초")
    for s in steps:
        print(f"  {s['단계']:<14} {s['결과']}" + (f" ({s['초']}초)" if s["초"] is not None else ""))
    try:
        auto = json.loads((CLEAN / "doc_vs_chain_auto_benji.json").read_text(encoding="utf-8"))
        head = (REPORTS / "benji_report.md").read_text(encoding="utf-8").splitlines()[0]
        print("\n  AI 자동 판정: " + ", ".join(f"{r['item']} → {r['verdict']}" for r in auto))
        print("  리포트 검사: " + re.sub(r"^<!--\s*|\s*-->$", "", head))
    except FileNotFoundError:
        print("\n  AI 결과 파일이 없습니다 (GPU 컴퓨터에서 한 번 실행 필요)")
    print(f"\n  리포트: reports/benji_report.md\n  Excel:  reports/{xlsx.name}")
    print("  대시보드: python -m streamlit run dashboard/app.py")
    print("=" * 64)

    if a.dashboard:
        subprocess.run([PY, "-m", "streamlit", "run", "dashboard/app.py", "--server.address", "localhost"], cwd=ROOT, env=ENV)
    return 0


LLM_HARNESS = ROOT / "llm" / "harness.py"

if __name__ == "__main__":
    sys.exit(main())
