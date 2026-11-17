# -*- coding: utf-8 -*-
"""관제실 백엔드. 스택 A의 LangGraph 그래프를 AG-UI 규약(ag-ui-langgraph)으로 열고,
Langfuse 추적 기록과 GPU 지표를 화면(console/)에 넘긴다. 빌드된 화면도 여기서 같이 서빙한다.

    venv_lg/Scripts/python.exe -m uvicorn console_api:api --port 8700
"""
import json, subprocess, time
from operator import add
from pathlib import Path
from typing import Annotated

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AnyMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

import report_agent as R
import stack_a as A   # 노드 함수, 모델, .env 읽기를 그대로 재사용
from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
from langfuse.langchain import CallbackHandler

HERE = Path(__file__).parent
ENV = dict(l.split("=", 1) for l in (HERE / ".env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
RUN_NAME = "stack-a 감사 조사"


class S(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]   # AG-UI가 대화 기록 자리로 쓴다
    queue: list
    case: str | None
    doc: dict
    evidence: dict
    claim: str
    verify: dict
    audit: dict
    report: dict
    results: list


g = StateGraph(S)
for n, f in [("총괄", A.supervisor), ("문서 분석", A.doc_analyst), ("조사", A.investigator), ("검증", A.verifier),
             ("감사", A.auditor), ("보고", R.reporter), ("결재", R.approver)]:
    g.add_node(n, f)
g.add_edge(START, "총괄")
g.add_conditional_edges("총괄", lambda s: "문서 분석" if s.get("case") else END, {"문서 분석": "문서 분석", END: END})
g.add_edge("문서 분석", "조사"); g.add_edge("조사", "검증"); g.add_edge("검증", "감사")
g.add_conditional_edges("감사", lambda s: "보고" if s["audit"]["pass"] else "총괄", {"보고": "보고", "총괄": "총괄"})
g.add_edge("보고", "결재")
g.add_edge("결재", "총괄")
graph = g.compile(checkpointer=InMemorySaver())

api = FastAPI(title="감사 관제실")
api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

add_langgraph_fastapi_endpoint(api, LangGraphAgent(
    name="audit", graph=graph, description="토큰화 펀드 배당 감사 조사",
    config={"callbacks": [CallbackHandler()], "run_name": RUN_NAME, "recursion_limit": 60,
            "metadata": {"langfuse_tags": ["stack-a", "console"]}}), path="/agent")


def _lf(path, **params):
    return requests.get(ENV["LANGFUSE_HOST"] + path, params=params, timeout=8,
                        auth=(ENV["LANGFUSE_PUBLIC_KEY"], ENV["LANGFUSE_SECRET_KEY"])).json()


def _s(v):
    return v if v is None or isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1)


TITLES = {k: v["title"] for k, v in A.CASES.items()}


@api.get("/api/traces")
def traces(limit: int = 5, hours: int = 48):
    """최근 조사 몇 회를 AgentPrism이 읽는 Langfuse 문서 형태({trace, observations})로.
    결재로 멈췄다 이어질 때마다 Langfuse 추적이 끊기므로, 같은 AG-UI 대화(thread_id)끼리 한 건으로 묶는다."""
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - hours * 3600))
    obs, cursor = [], None
    for _ in range(10):
        page = _lf("/api/public/v2/observations", limit=1000, fromStartTime=since,
                   fields="core,basic,time,io,metadata,usage", **({"cursor": cursor} if cursor else {}))
        obs += page.get("data", [])
        cursor = (page.get("meta") or {}).get("cursor")
        if not cursor or not page.get("data"):
            break
    roots = [o for o in obs if o.get("name") == RUN_NAME]
    threads: dict[str, list] = {}
    for r in roots:
        threads.setdefault((r.get("metadata") or {}).get("thread_id") or r["traceId"], []).append(r)
    out = []
    for tid, rs in sorted(threads.items(), key=lambda kv: min(r["startTime"] for r in kv[1]), reverse=True)[:limit]:
        tids = {r["traceId"] for r in rs}
        rows = []
        for o in obs:
            if o["traceId"] not in tids or o.get("name") == "<unknown>":   # 갈림길 판단 함수는 숨긴다
                continue
            o = {**o, "input": _s(o.get("input")), "output": _s(o.get("output"))}
            if o["name"] == RUN_NAME:   # 결재로 나뉜 구간마다 맨 위 칸. 그 구간이 다룬 조사 주제로 이름을 붙인다
                case = None
                try:
                    case = json.loads(o["output"] or "{}").get("case") or json.loads(o["input"] or "{}").get("case")
                except Exception:
                    pass
                o = {**o, "parentObservationId": None, "name": f"구간 · {TITLES.get(case, '마무리')}"}
            rows.append(o)
        rows.sort(key=lambda o: o["startTime"])
        t0 = min(_ts(r["startTime"]) for r in rs)
        t1 = max(_ts(o.get("endTime") or o["startTime"]) for o in rows)
        gens = [o for o in rows if o.get("type") == "GENERATION"]
        tokens = sum((o.get("usageDetails") or {}).get("total", 0) or 0 for o in gens)
        out.append({"trace": {"id": tid, "name": RUN_NAME, "timestamp": rs[0]["startTime"]},
                    "record": {"id": tid, "name": time.strftime("%m월 %d일 %H:%M 조사", time.localtime(t0)),
                               "spansCount": len(rows), "durationMs": int((t1 - t0) * 1000),
                               "agentDescription": f"LLM 호출 {len(gens)}회 · 결재 구간 {len(rs)}개",
                               "startTime": int(t0 * 1000), "totalTokens": int(tokens)},
                    "observations": rows})
    return out


def _ts(iso):
    from datetime import datetime
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


@api.get("/api/metrics")
def metrics():
    """GPU 사용률·메모리, 지금 올라와 있는 모델."""
    gpu = {}
    try:
        q = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4).stdout.strip().split(", ")
        gpu = {"util": float(q[0]), "mem_used": float(q[1]), "mem_total": float(q[2]), "temp": float(q[3]), "power": float(q[4])}
    except Exception:
        pass
    try:
        models = [m["name"] for m in requests.get("http://localhost:11434/api/ps", timeout=3).json().get("models", [])]
    except Exception:
        models = []
    return {"t": time.time(), "gpu": gpu, "models": models, "model": A.MODEL}


dist = HERE / "console" / "dist"
if dist.exists():
    api.mount("/", StaticFiles(directory=dist, html=True), name="ui")
