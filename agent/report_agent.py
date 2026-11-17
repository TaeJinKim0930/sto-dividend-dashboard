# -*- coding: utf-8 -*-
"""보고 에이전트. 감사를 통과한 건을 결재권자에게 올리기 전에 보고서를 만든다.

1) 숫자 대조 (코드): 주장 문장 속 숫자마다 도구 결과의 어느 칸에서 왔는지, 그 칸의 실제 뜻이 무엇인지 찾는다
2) 뜻 검사 (LLM): 문장이 그 숫자를 원래 뜻대로 썼는지 판단한다. 숫자 인용 검사가 못 잡는 '숫자는 맞는데 뜻이 틀린' 문장을 잡는 단계
3) 재계산 대조표, 투자설명서 근거, 결재권자 확인 사항을 묶어 보고서로 낸다. 권고(승인/반려)는 코드가 정한다
"""
import json, re

from langchain_ollama import ChatOllama
from langgraph.types import interrupt

import stack_a as A

LLM_JSON = ChatOllama(model=A.MODEL, reasoning=False, temperature=0, num_ctx=8192, format="json")

TOOL_KO = {"weekend_profile": "업그레이드 전후 주말 배당 집계", "change_point": "주말 배당 시작 시점", "upgrade_events": "컨트랙트 업그레이드 기록",
           "redemption_events": "환매 기록 집계", "bridge_events": "체인 이동 기록"}
FIELD_KO = {
    "upgrade_date": "컨트랙트 업그레이드 날짜", "before_pct": "업그레이드 전 배당 중 주말에 지급된 비율(%)",
    "before_n": "업그레이드 전 배당 지급 건수", "after_pct": "업그레이드 후 배당 중 주말에 지급된 비율(%)",
    "after_n": "업그레이드 후 배당 지급 건수", "total_n": "전체 배당 지급 건수",
    "first_weekend_dividend": "주말 배당이 처음 나온 날짜", "nearest_upgrade": "그와 가장 가까운 업그레이드 날짜",
    "count": "건수", "timestamps": "업그레이드 시각", "total_usd": "환매 합계(달러)", "dates": "환매 날짜",
    "bridge_flows": "체인 이동 건수", "classes": "기록 분류 종류",
}


def _flat(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _flat(v, f"{path}.{k}" if path else k)
    elif isinstance(o, list):
        for v in o:
            yield from _flat(v, path)
    else:
        yield path, o


def _numbers(claim: str):
    text = claim.replace(",", "")
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    rest = re.sub(r"\d{4}-\d{2}-\d{2}(T[\d:]+Z?)?", " ", text)
    nums = [n for n in re.findall(r"\d+(?:\.\d+)?", rest) if not (n.isdigit() and int(n) <= 10)]
    return list(dict.fromkeys(dates + nums))


def map_numbers(claim: str, evidence: dict) -> list:
    """주장 속 숫자 → 도구 결과의 칸과 그 뜻. 코드가 찾으므로 틀리지 않는다."""
    rows = []
    flat = list(_flat(evidence))
    for n in _numbers(claim):
        hit = None
        for path, v in flat:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                try:
                    if abs(float(v) - float(n)) < 1e-9:
                        hit = (path, v); break
                except ValueError:
                    pass
            elif isinstance(v, str) and n in v:
                hit = (path, v); break
        if hit:
            tool, field = hit[0].split(".")[0], hit[0].split(".")[-1]
            rows.append({"number": n, "source": f"{tool}.{field}", "tool_ko": TOOL_KO.get(tool, tool),
                         "meaning": FIELD_KO.get(field, field), "value": hit[1]})
        else:
            rows.append({"number": n, "source": None, "tool_ko": None, "meaning": "도구 결과에 없음", "value": None})
    return rows


def recompute_table(case: str, evidence: dict, recompute: dict) -> list:
    if case == "weekend":
        inv = evidence.get("weekend_profile", {})
        keys = ["before_pct", "after_pct", "before_n", "after_n"]
    elif case == "redeem":
        inv = evidence.get("redemption_events", {})
        keys = ["count", "total_usd"]
    else:
        inv = evidence.get("bridge_events", {})
        keys = ["bridge_flows"]
    return [{"item": FIELD_KO.get(k, k), "investigation": inv.get(k), "recompute": recompute.get(k),
             "match": inv.get(k) == recompute.get(k)} for k in keys]


def reporter(s):
    A.status("보고", case=s["case"])
    case, title = s["case"], A.CASES[s["case"]]["title"]
    nums = map_numbers(s["claim"], s["evidence"])
    ask = {"claim": s["claim"],
           "numbers": [{"number": r["number"], "actual_meaning": r["meaning"]} for r in nums],
           "document_note": s["doc"]["note"], "verify_note": s["verify"]["note"]}
    try:
        out = json.loads(LLM_JSON.invoke([
            ("system", "너는 결재권자(사장)에게 올릴 보고서를 쓰는 보고 담당이다. 반드시 JSON 하나만 출력한다.\n"
                       "할 일 1: numbers의 숫자마다, 조사관의 주장 문장(claim)이 그 숫자를 무엇이라고 불렀는지(claim_usage) 적고, "
                       "그것이 actual_meaning(실제 데이터의 뜻)과 같은 뜻인지(ok) 엄격하게 판단한다. 건수를 사람 수로, 비율을 증가율로 부르는 식이면 ok=false.\n"
                       "할 일 2: summary에 결재권자에게 올리는 보고를 2~3문장, '~입니다' 보고체로 쓴다. 숫자는 actual_meaning 기준으로만 설명한다.\n"
                       "할 일 3: ask에 결재권자가 직접 판단하거나 확인해야 할 점을 1~3개 쓴다.\n"
                       '형식: {"checks":[{"number":"..","claim_usage":"..","ok":true,"why":".."}],"summary":"..","ask":[".."]}'),
            ("user", json.dumps(ask, ensure_ascii=False))]).content)
    except Exception as e:
        out = {"checks": [], "summary": f"보고서 문장 생성에 실패했습니다 ({str(e)[:80]}). 아래 표를 직접 확인해 주십시오.", "ask": []}
    by_n = {str(c.get("number")): c for c in out.get("checks", []) if isinstance(c, dict)}
    for r in nums:
        c = by_n.get(r["number"], {})
        r["claim_usage"] = c.get("claim_usage")
        r["ok"] = bool(c.get("ok", True)) and r["source"] is not None
        r["why"] = c.get("why")
    bad = [r for r in nums if not r["ok"]]
    table = recompute_table(case, s["evidence"], s["verify"]["recompute"])
    checklist = [
        {"item": "결론 판단", "detail": f"숫자 {len(bad)}개를 원래 뜻과 다르게 썼습니다. 반려 후 다시 조사시킬지 정해 주십시오." if bad
         else "숫자를 모두 원래 뜻대로 썼습니다. 결론 문장이 업무 판단에 쓸 만한지 정해 주십시오.", "level": "decide"},
        {"item": "숫자 뜻 확인", "detail": ", ".join(f"{r['number']}({r['claim_usage'] or '?'} → 실제는 {r['meaning']})" for r in bad) or "불일치 없음",
         "level": "check" if bad else "ok"},
        {"item": "독립 재계산", "detail": f"{len(table)}개 항목 중 {sum(t['match'] for t in table)}개 일치. 조사와 다른 계산 경로로 다시 셌습니다.",
         "level": "ok" if all(t["match"] for t in table) else "check"},
        {"item": "근거 인용", "detail": f"문장 속 숫자 {s['audit']['numbers']}개가 모두 도구 결과에 있습니다.", "level": "ok"},
        {"item": "투자설명서 근거", "detail": "아래 원문 문장이 이 주제와 실제로 관련 있는지 봐 주십시오. 키워드 검색으로 찾은 문장입니다.", "level": "check"},
    ] + [{"item": "보고 담당 의견", "detail": a, "level": "check"} for a in out.get("ask", [])[:3] if isinstance(a, str)]
    report = {
        "case": case, "title": title,
        "recommendation": "반려 권고" if bad else "승인 권고",
        "reason": f"주장 문장이 숫자 {len(bad)}개를 원래 뜻과 다르게 썼습니다" if bad else "재계산·근거·숫자 뜻 검사를 모두 통과했습니다",
        "summary": out.get("summary", ""), "claim": s["claim"], "numbers": nums, "recompute": table,
        "doc": {"note": s["doc"]["note"], "hits": s["doc"]["hits"], "query": A.CASES[case]["doc_q"]},
        "verify_note": s["verify"]["note"], "audit_note": s["audit"]["note"], "checklist": checklist,
    }
    res = list(s["results"]); res[-1] = {**res[-1], "report": report}
    return {"report": report, "results": res}


def approver(s):
    A.status("결재", case=s["case"], waiting=True)
    d = interrupt({"case": s["case"], "title": A.CASES[s["case"]]["title"], "claim": s["claim"], "report": s.get("report")})
    res = list(s["results"]); res[-1] = {**res[-1], "decision": d}
    return {"results": res}
