# -*- coding: utf-8 -*-
"""관제실 효과 측정. 같은 조사 3건을 N회 돌려, 각 단계가 무엇을 걸렀는지 센다.

- 감사(근거 인용 검사): 문장 속 숫자가 도구 결과에 있는지만 본다
- 보고(숫자 뜻 검사): 그 숫자를 원래 뜻대로 썼는지까지 본다
- 결재는 보고 에이전트의 권고대로 자동 입력 (사람 대신)

    venv_lg/Scripts/python.exe eval_report_agent.py 20         # 조사 문장 온도 0 (매번 같은 문장)
    venv_lg/Scripts/python.exe eval_report_agent.py 20 0.7     # 온도 0.7 (문장이 매번 달라짐)
결과: eval/report_eval_YYYYMMDD_HHMM.json, .md
"""
import json, sys, time
from pathlib import Path

from langgraph.types import Command

import console_api as C   # 관제실과 같은 그래프 (총괄 → … → 보고 → 결재)

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
TEMP = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
if TEMP:   # 문서 분석·조사·검증·감사 문장을 쓰는 LLM만 바꾼다. 보고 에이전트(뜻 검사)는 그대로 온도 0
    from langchain_ollama import ChatOllama
    C.A.LLM = ChatOllama(model=C.A.MODEL, reasoning=False, temperature=TEMP, num_ctx=8192)
OUT = Path(__file__).parent / "eval"; OUT.mkdir(exist_ok=True)
stamp = time.strftime("%Y%m%d_%H%M") + (f"_t{TEMP}" if TEMP else "")
# 사람이 쓸 낱말을 숫자에 붙인 경우를 '뜻 오류 의심'으로 따로 센다 (보고 에이전트 판단과 비교용 단순 규칙)
SUSPECT = ["사용자", "명에서", "명으로", "고객", "투자자 수", "증가율"]

rows = []
for i in range(N):
    cfg = {"configurable": {"thread_id": f"eval-{stamp}-{i}"}, "recursion_limit": 60}
    t0 = time.time()
    inp = {"queue": [], "case": None, "results": []}
    decisions = []
    while True:
        for _ in C.graph.stream(inp, cfg, stream_mode="updates"):
            pass
        st = C.graph.get_state(cfg)
        if not st.next:
            break
        pend = st.tasks[0].interrupts[0].value
        rep = pend.get("report") or {}
        d = "반려" if rep.get("recommendation") == "반려 권고" else "승인"
        decisions.append(d)
        inp = Command(resume=d)
    sec = time.time() - t0
    for r in C.graph.get_state(cfg).values.get("results", []):
        rep = r.get("report") or {}
        bad = [n for n in rep.get("numbers", []) if not n.get("ok")]
        rows.append({
            "run": i, "case": r["case"], "claim": r["claim"],
            "verify_audit_pass": r["pass"],                       # 검증·감사(근거 인용) 둘 다 통과했나
            "report": rep.get("recommendation"),                   # 보고 에이전트 권고 (감사 통과 건만)
            "meaning_errors": [f"{n['number']}: {n.get('claim_usage')} → {n['meaning']}" for n in bad],
            "suspect_words": [w for w in SUSPECT if w in r["claim"]],
            "decision": r.get("decision"), "run_sec": round(sec, 1),
        })
    print(f"[{i + 1}/{N}] {sec:.1f}s decisions={decisions}", flush=True)

# 요약
def cnt(f):
    return sum(1 for r in rows if f(r))

passed = [r for r in rows if r["verify_audit_pass"]]
summary = {
    "runs": N, "items": len(rows),
    "avg_run_sec": round(sum({r["run"]: r["run_sec"] for r in rows}.values()) / N, 1),
    "rejected_by_code": cnt(lambda r: not r["verify_audit_pass"]),
    "passed_citation_check": len(passed),
    "report_reject": cnt(lambda r: r["verify_audit_pass"] and r["report"] == "반려 권고"),
    "report_approve": cnt(lambda r: r["verify_audit_pass"] and r["report"] == "승인 권고"),
    "suspect_words_in_passed": cnt(lambda r: r["verify_audit_pass"] and r["suspect_words"]),
    "suspect_and_report_reject": cnt(lambda r: r["verify_audit_pass"] and r["suspect_words"] and r["report"] == "반려 권고"),
    "no_suspect_but_report_reject": cnt(lambda r: r["verify_audit_pass"] and not r["suspect_words"] and r["report"] == "반려 권고"),
    "by_case": {c: {"items": cnt(lambda r, c=c: r["case"] == c),
                    "passed": cnt(lambda r, c=c: r["case"] == c and r["verify_audit_pass"]),
                    "report_reject": cnt(lambda r, c=c: r["case"] == c and r["report"] == "반려 권고")}
                for c in ("weekend", "redeem", "bridge")},
}
(OUT / f"report_eval_{stamp}.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")

s = summary
md = [f"# 관제실 효과 측정 ({time.strftime('%Y-%m-%d %H:%M')}, 모델 {C.A.MODEL}, 조사 문장 온도 {TEMP})", "",
      f"- 조사 3건 × {N}회 = {s['items']}건, 1회(3건) 평균 {s['avg_run_sec']}초 (결재는 보고 에이전트 권고대로 자동)",
      f"- 코드 판정(검증·근거 인용)에서 기각: {s['rejected_by_code']}건 — 체인 이동 가설 등 데이터가 뒷받침하지 않는 주장",
      f"- 근거 인용 검사 통과: {s['passed_citation_check']}건 → 보고 에이전트 반려 권고 {s['report_reject']}건, 승인 권고 {s['report_approve']}건",
      f"- 통과 건 중 '사용자·명·고객·증가율' 등 뜻 오류 의심 낱말이 있는 문장: {s['suspect_words_in_passed']}건, 그중 보고 에이전트가 반려 권고: {s['suspect_and_report_reject']}건",
      f"- 의심 낱말이 없는데 반려 권고 (과잉 반려 후보, 사람이 확인): {s['no_suspect_but_report_reject']}건", "",
      "| 조사 | 건수 | 근거 인용 통과 | 보고 반려 권고 |", "|---|---|---|---|"]
for c, v in s["by_case"].items():
    md.append(f"| {c} | {v['items']} | {v['passed']} | {v['report_reject']} |")
md += ["", "## 반려 권고 문장과 이유", ""]
for r in rows:
    if r["report"] == "반려 권고":
        md.append(f"- [{r['run']}회 {r['case']}] {r['claim']}")
        for e in r["meaning_errors"]:
            md.append(f"  - {e}")
(OUT / f"report_eval_{stamp}.md").write_text("\n".join(md), encoding="utf-8")
print("\n".join(md[:9]), flush=True)
