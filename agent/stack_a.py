# -*- coding: utf-8 -*-
"""스택 A: LangGraph + Ollama + Langfuse 추적 + LangGraphics 실시간 그래프 (http://localhost:8764/?ws_port=8766).
조사 대상 3건을 차례로: 총괄 → 문서 분석 → 조사 → 검증 → 감사 → (통과 시) 결재 → 총괄 …
흐름과 도구 호출은 코드, LLM은 문장만 쓴다.

    python stack_a.py   서버 상주. ctl/a_run 파일이 생기면 조사 시작, 결재는 ctl/a_decision 파일로 받음 (비교 페이지 버튼)
"""
import json, os, time
from pathlib import Path
from typing import TypedDict

from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import tools

HERE = Path(__file__).parent
CTL = HERE / "ctl"; CTL.mkdir(exist_ok=True)
for line in (HERE / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
os.environ.setdefault("LANGFUSE_BASE_URL", os.environ.get("LANGFUSE_HOST", ""))
from langfuse import get_client
from langfuse.langchain import CallbackHandler

MODEL = "gemma4:26b-a4b-it-qat"
LLM = ChatOllama(model=MODEL, reasoning=False, temperature=0, num_ctx=8192)

CASES = {
    "weekend": {"title": "BENJI 주말 배당은 왜 시작됐나", "doc_q": "declare dividends net asset value calculation"},
    "redeem": {"title": "11월 4일 대규모 환매는 기록과 맞나", "doc_q": "redemption proceeds shares redeem"},
    "bridge": {"title": "가설: 주말 배당은 다른 체인으로 옮긴 물량 때문", "doc_q": "blockchain network transfer shares"},
}


class S(TypedDict, total=False):
    queue: list
    case: str
    doc: dict
    evidence: dict
    claim: str
    verify: dict
    audit: dict
    results: list


def ask(system, user):
    return LLM.invoke([("system", system), ("user", user)]).content.strip()


def status(node, **kw):
    (CTL / "a_status.json").write_text(json.dumps({"node": node, "t": time.time(), **kw}, ensure_ascii=False), encoding="utf-8")


def supervisor(s: S):
    q = list(s.get("queue") or [])
    if s.get("case") is None and not s.get("results"):
        q = list(CASES)
    nxt = q.pop(0) if q else None
    status("총괄", case=nxt)
    return {"queue": q, "case": nxt}


def doc_analyst(s: S):
    status("문서 분석", case=s["case"])
    hit = tools.prospectus_search(CASES[s["case"]]["doc_q"])
    note = ask("너는 투자설명서 분석가다. 주어진 원문 문장만 근거로 한국어 1문장으로 요약한다.", json.dumps(hit, ensure_ascii=False))
    return {"doc": {"hits": hit["hits"], "note": note}}


def investigator(s: S):
    status("조사", case=s["case"])
    c = s["case"]
    if c == "weekend":
        ev = {"weekend_profile": tools.weekend_profile(), "change_point": tools.detect_change_point(), "upgrade_events": tools.upgrade_events()}
    elif c == "redeem":
        ev = {"redemption_events": tools.redemption_events()}
    else:
        ev = {"bridge_events": tools.bridge_events()}
    claim = ask("너는 토큰화 펀드 온체인 조사관이다. 도구 결과의 숫자만 써서 한국어 2문장으로 발견을 쓴다. 단정하지 않는다.",
                f"조사 주제: {CASES[c]['title']}\n도구 결과: {json.dumps(ev, ensure_ascii=False)}")
    return {"evidence": ev, "claim": claim}


def verifier(s: S):
    status("검증", case=s["case"])
    c, ev = s["case"], s["evidence"]
    if c == "weekend":
        re_ = tools.recompute_weekend(); wp = ev["weekend_profile"]
        ok = all(re_[k] == wp[k] for k in ("before_pct", "after_pct", "before_n", "after_n"))
    elif c == "redeem":
        re_ = tools.recompute_burn(); r = ev["redemption_events"]
        ok = re_["count"] == r["count"] and abs(re_["total_usd"] - r["total_usd"]) < 0.01
    else:
        re_ = {"bridge_flows": ev["bridge_events"]["bridge_flows"]}
        ok = False   # 체인 이동이 0건이면 가설 기각
    note = ask("너는 검증관이다. 독립 재계산 결과와 코드 판정을 한국어 1문장으로 설명한다.",
               f"주제: {CASES[c]['title']}\n조사: {json.dumps(ev, ensure_ascii=False)}\n재계산: {json.dumps(re_, ensure_ascii=False)}\n코드 판정: {'통과' if ok else '기각'}")
    return {"verify": {"recompute": re_, "pass": ok, "note": note}}


def auditor(s: S):
    status("감사", case=s["case"])
    chk = tools.check_citations(s["claim"], json.dumps(s["evidence"], ensure_ascii=False))
    ok = chk["pass"] and s["verify"]["pass"]
    note = ask("너는 감사관이다. 근거 인용 검사와 검증 결과를 한국어 1문장으로 쓴다.",
               json.dumps({"citations": chk, "verified": s["verify"]["pass"]}, ensure_ascii=False))
    res = {"case": s["case"], "title": CASES[s["case"]]["title"], "claim": s["claim"], "doc": s["doc"]["note"],
           "verify": s["verify"]["note"], "audit": note, "pass": ok, "decision": None if ok else "검증에서 기각"}
    return {"audit": {**chk, "pass": ok, "note": note}, "results": (s.get("results") or []) + [res]}


def human(s: S):
    status("결재", case=s["case"], waiting=True)
    d = interrupt({"case": s["case"], "title": CASES[s["case"]]["title"], "claim": s["claim"]})
    res = list(s["results"]); res[-1] = {**res[-1], "decision": d}
    return {"results": res}


g = StateGraph(S)
for n, f in [("총괄", supervisor), ("문서 분석", doc_analyst), ("조사", investigator), ("검증", verifier), ("감사", auditor), ("결재", human)]:
    g.add_node(n, f)
g.add_edge(START, "총괄")
g.add_conditional_edges("총괄", lambda s: "문서 분석" if s.get("case") else END, {"문서 분석": "문서 분석", END: END})
g.add_edge("문서 분석", "조사"); g.add_edge("조사", "검증"); g.add_edge("검증", "감사")
g.add_conditional_edges("감사", lambda s: "결재" if s["audit"]["pass"] else "총괄", {"결재": "결재", "총괄": "총괄"})
g.add_edge("결재", "총괄")
app = g.compile(checkpointer=InMemorySaver())


def run_once(runner):
    t0 = time.time()
    cfg = {"configurable": {"thread_id": f"a-{int(t0)}"}, "callbacks": [CallbackHandler()],
           "metadata": {"langfuse_tags": ["stack-a"]}, "run_name": "stack-a 감사 조사", "recursion_limit": 60}
    inp = {"queue": [], "case": None, "results": []}
    while True:
        for _ in runner.stream(inp, cfg, stream_mode="updates"):
            pass
        st = app.get_state(cfg)
        if not st.next:
            break
        pend = st.tasks[0].interrupts[0].value if st.tasks and st.tasks[0].interrupts else {}
        (CTL / "a_pending.json").write_text(json.dumps(pend, ensure_ascii=False), encoding="utf-8")
        dec_f = CTL / "a_decision"
        while not dec_f.exists():
            time.sleep(0.5)
        decision = dec_f.read_text(encoding="utf-8").strip() or "승인"
        dec_f.unlink(); (CTL / "a_pending.json").unlink(missing_ok=True)
        inp = Command(resume=decision)
    res = app.get_state(cfg).values.get("results", [])
    (CTL / "a_last.json").write_text(json.dumps({"seconds": round(time.time() - t0, 1), "model": MODEL, "finished": time.strftime("%H:%M:%S"),
                                                 "results": res}, ensure_ascii=False, indent=1), encoding="utf-8")
    status("끝", case=None)
    get_client().flush()


if __name__ == "__main__":
    from langgraphics import watch
    runner = watch(app, port=8764, ws_port=8766, open_browser=False, inspect="full")
    status("대기", case=None)
    print("serve: ctl/a_run 을 기다림", flush=True)
    while True:
        trig = CTL / "a_run"
        if trig.exists():
            trig.unlink()
            print("run start", time.strftime("%H:%M:%S"), flush=True)
            try:
                run_once(runner)
            except Exception as e:
                status("오류", error=str(e)[:300]); print("error", e, flush=True)
            print("run end", time.strftime("%H:%M:%S"), flush=True)
        time.sleep(0.5)
