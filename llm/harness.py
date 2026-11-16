# -*- coding: utf-8 -*-
"""LLM 하네스 v2.2 — 투자설명서 조건 추출 → 검증 → 온체인 대조 → 리포트 작성.

설계 원칙
  1. LLM은 '읽고 쓰는' 일만 한다. 판정(일치/검토 필요)과 추론은 파이썬 규칙이 한다 → 재현 가능
  2. LLM 출력은 그대로 믿지 않는다
     - 스키마 검사: 정해진 JSON 구조가 아니면 재시도
     - 문장 번호 인용: 발췌문 문장마다 [S번호]를 붙이고, LLM은 근거를 베끼지 않고 번호로 가리킨다
     - 근거-값 일치 검사: 값의 핵심 단어가 가리킨 문장에 실제로 있어야 채택 (엉뚱한 근거 차단)
     - 다수결: 같은 추출을 N회 반복, 표기를 정리한 값끼리 묶어 일치율을 신뢰도로 기록
     - 숫자 검사: LLM이 쓴 문장에 입력에 없던 숫자가 있으면 표시
  3. 리포트의 뼈대(판정별 절, 인용문, 수치, 데이터 범위)는 코드가 만들고, LLM은 요약과 '검토가 필요한 이유'만 쓴다
  4. 모든 프롬프트·원응답·결과를 llm/runs/ 에 남긴다

v1 → v2 (2026-10-18 GPU 실제 실행에서 드러난 문제를 고침, 자세한 내용은 llm/README.md)
  - 주말 선언 여부를 LLM이 추론하게 했더니 3개 모델 모두 5회 다 '언급 없음' → 사실 2개(선언 시점, NAV 계산일)만 뽑고 코드가 잇는다
  - 근거 문장을 베끼게 했더니 "(NAV)" 누락·"0.20 %" 붙여쓰기로 맞는 값이 거부됨 → 문장 번호로 가리킨다
  - 값과 무관한 문장을 근거로 붙여도 통과했음 → 근거-값 일치 검사 추가
  - 리포트가 '확인 불가'를 '검토 필요' 절에 넣고 업그레이드 날짜를 데이터 기간으로 씀 → 뼈대는 코드가, 기간은 입력에 명시
  - "a" 유무 같은 표기 차이를 다른 값으로 세어 일치율이 낮게 나옴 → 표기 정리 후 다수결
v2 → v2.1: 무관한 근거 번호 정리, 단정·당위 표현 검사, rescore(저장된 원응답 재채점), 기본 모델 phi4:14b
v2.1 → v2.2: 프롬프트 규칙만으로는 phi4가 '상충'·'선언되어야 하므로'를 계속 씀 (2회 중 2회)
  - 표현 검사를 단어 목록에서 당위 어미 패턴으로 넓힘
  - 피드백 재시도: 숫자·표현 검사에 걸리면 걸린 내용을 알려 주고 같은 대화에서 다시 쓰게 함 (최대 3회, 모든 시도 기록)

사용
  python llm/harness.py all --fund BENJI --runs 5          # GPU 컴퓨터 (Ollama)
  python llm/harness.py all --fund BENJI --runs 3 --dry-run # LLM 없이 하네스 동작 시험
환경변수(.env): OLLAMA_URL (기본 http://localhost:11434), OLLAMA_MODEL (기본 phi4:14b), OLLAMA_NUM_CTX (기본 16384)
"""
import argparse, json, os, re, time
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

HARNESS = "v2.2"
DEFAULT_MODEL = "phi4:14b"   # 2026-10-18 3개 모델 비교 후 선택 (llm/README.md "최종 모델 선택")
ROOT = Path(__file__).resolve().parents[1]
LLM = ROOT / "llm"
CLEAN = ROOT / "검증" / "data" / "clean"
DOCS = ROOT / "검증" / "data" / "docs"
REPORTS = ROOT / "reports"
FIELDS = ["dividend_declaration_timing", "nav_calculation_days", "dividend_payment_form",
          "reinvestment_frequency", "fund_closed_days", "share_price_target", "expense_ratio", "official_record"]
FUNDS = {
    "BENJI": {"name": "Franklin OnChain U.S. Government Money Fund",
              "doc": DOCS / "benji_485bpos_2026-08-01.txt",
              "source": "SEC EDGAR 485BPOS, 2026-08-01",
              "chain": "Ethereum"},
}
KEYWORDS = ["declare", "dividend", "distribution", "net asset value", "nav", "reinvest", "closed",
            "holiday", "weekend", "operating expenses", "official record", "transfer agent", "$1.00",
            "share price", "blockchain", "open for business"]


def env(key, default=None):
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return os.environ.get(key, default)


def norm(s):
    return re.sub(r"\s+", " ", str(s).replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()


# ---------------- 프롬프트 ----------------
def load_prompt(name):
    t = (LLM / "prompts" / name).read_text(encoding="utf-8")
    system = t.split("## [SYSTEM]", 1)[1].split("## [USER]", 1)[0].strip()
    user = t.split("## [USER]", 1)[1].strip()
    return system, user


def load_schema(name):
    return json.loads((LLM / "schema" / name).read_text(encoding="utf-8"))


# ---------------- 1. 검색: 긴 문서에서 관련 문장만, 문장마다 번호 ----------------
FIELD_KEYS = {   # 항목별 검색어 — 항목마다 근거 문장을 먼저 확보한다
    "dividend_declaration_timing": ["declare", "dividend"],
    "nav_calculation_days": ["calculates its nav", "open for business", "nyse"],
    "dividend_payment_form": ["reinvested", "additional shares", "cash"],
    "reinvestment_frequency": ["reinvest", "daily", "monthly"],
    "fund_closed_days": ["closed", "weekend", "holiday"],
    "share_price_target": ["$1.00", "share price", "stable"],
    "expense_ratio": ["operating expenses", "fee waiver", "expense reimbursement"],
    "official_record": ["official record", "transfer agent", "blockchain"],
}


def retrieve(text, max_chars=12000, window=1, per_field=2):
    """1) 항목마다 그 항목 검색어가 가장 많이 겹치는 문장 per_field개를 먼저 확보
       2) 남은 한도는 전체 검색어 점수 순으로 채운다
       (전체 점수만 쓰면 '주말 휴장'처럼 검색어가 적은 핵심 문장이 밀려난다 — 실제로 발생)
       반환: 이어진 문장 묶음의 목록 (묶음 = 문장 목록)"""
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text)
    low = [s.lower() for s in sents]
    picked, total = set(), 0

    def take(i):
        nonlocal total
        span = set(range(max(0, i - window), min(len(sents), i + window + 1))) - picked
        add = sum(len(sents[j]) for j in span)
        if total + add > max_chars:
            return False
        picked.update(span)
        total += add
        return True

    for keys in FIELD_KEYS.values():
        sc = [sum(k in l for k in keys) for l in low]
        for i in sorted(range(len(sents)), key=lambda i: -sc[i])[:per_field]:
            if sc[i] >= min(2, len(keys)):
                take(i)
    score = [sum(k in l for k in KEYWORDS) for l in low]
    for i in sorted(range(len(sents)), key=lambda i: -score[i]):
        if score[i] < 2:
            break
        take(i)
    idx = sorted(picked)
    chunks, cur = [], [idx[0]] if idx else []
    for a, b in zip(idx, idx[1:]):
        if b == a + 1:
            cur.append(b)
        else:
            chunks.append(cur); cur = [b]
    if cur:
        chunks.append(cur)
    return [[sents[j] for j in c] for c in chunks]


def number_excerpts(chunks):
    """문장마다 [S번호]를 붙인다. LLM은 근거를 베끼지 않고 이 번호로 가리킨다 → 인용 복사 실수가 원천적으로 없다."""
    sid, blocks = {}, []
    for c in chunks:
        parts = []
        for s in c:
            sid[len(sid) + 1] = s
            parts.append(f"[S{len(sid)}] {s}")
        blocks.append(" ".join(parts))
    return "\n\n".join(blocks), sid


# ---------------- 2. LLM 호출 ----------------
def call_ollama(system, user, schema=None, temperature=0.0, history=None):
    # num_ctx: Ollama 기본 문맥(약 4천 토큰)으로는 발췌 1.2만 자 + 지시문이 넘쳐 앞부분(규칙)이 조용히 잘린다
    # history: 검사에 걸린 앞 답변과 고칠 점(피드백 재시도). 같은 대화로 이어서 다시 쓰게 한다
    body = {"model": env("OLLAMA_MODEL", DEFAULT_MODEL), "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}] + (history or []),
            "options": {"temperature": temperature, "num_ctx": int(env("OLLAMA_NUM_CTX", "16384"))}}
    if schema is not None:
        body["format"] = schema
    r = requests.post(env("OLLAMA_URL", "http://localhost:11434") + "/api/chat", json=body, timeout=600)
    r.raise_for_status()
    return r.json()["message"]["content"]


def find_ids(sid, phrase):
    p = norm(phrase)
    return [k for k, s in sid.items() if p in norm(s)][:1]


def call_mock(kind, run, sid=None):
    """LLM 없이 하네스를 시험하는 가짜 응답. 일부러 틀린 번호·값과 없는 숫자를 섞는다."""
    if kind == "extract":
        f = lambda p: find_ids(sid, p)
        rec = ("a proprietary blockchain-integrated system", "proprietary blockchain-integrated system",
               "A proprietary blockchain-integrated system")[run % 3]          # 표기만 다름 → 같은 값으로 묶여야 함
        real = {
            "dividend_declaration_timing": ("each day when it makes its final NAV calculation",
                                            f("final net asset value (NAV) calculation")),
            "nav_calculation_days": ("every day on which both the NYSE and FRBNY are open for business",
                                     f("calculates its NAV every day")),
            "dividend_payment_form": ("additional shares", f("automatically reinvested in additional shares")),
            "reinvestment_frequency": ("daily", f("reinvests them daily")),
            "fund_closed_days": ("weekends and holidays", f("closed on weekends") + f("following holidays are observed")),
            "share_price_target": ("$1.00", [999]),                                    # 없는 번호 → 거부돼야 함
            "expense_ratio": ("0.35%", f("operating expenses after fee waiver")),       # 근거에 없는 값 → 거부돼야 함
            "official_record": (rec, f("official record of share ownership")),
        }
        if run == 1:   # 실제 GPU 실행에서 본 실수: 값은 맞는데 엉뚱한 문장을 근거로 → 거부돼야 함
            real["reinvestment_frequency"] = ("daily", f("automatically reinvested in additional shares"))
        if run == 2:   # 값이 흔들리는 상황 → 근거와 안 맞아 거부, 다수결 일치율이 내려가야 함
            real["reinvestment_frequency"] = ("monthly", f("reinvests them daily"))
        return json.dumps({k: {"value": v, "evidence_ids": e} for k, (v, e) in real.items()})
    if run == 0:
        # 1회차: 9,999,999는 입력에 없는 숫자, 27.3은 그럴듯하지만 입력(10-06 27.4, 11-15 27.5)과 다른 숫자,
        # '상충'·'선언되어야 하므로'는 v2·v2.1 실제 실행에서 phi4가 쓴 표현 → 모두 걸려 피드백 재시도가 돌아야 함
        # '보수'는 검토 필요 항목이 아님 → 버려져야 함
        return json.dumps({
            "summary": "BENJI는 2025-05-23 업그레이드 뒤 주말에도 배당을 발행해 문서와 상충됨. 전체 배당 총액은 9,999,999달러다.",
            "reasons": [{"item": "배당 선언일 (주말·휴일 포함 여부)",
                         "reason": "배당은 개장일에만 선언되어야 하므로 업그레이드 뒤 주말 지급 비율 27.3%는 문제다."},
                        {"item": "보수", "reason": "보수가 문서와 다를 수 있음."}]}, ensure_ascii=False)
    return json.dumps({   # 피드백 뒤: 문서 사실과 관측된 차이만. 비율 숫자는 데이터 갱신마다 바뀌므로 넣지 않는다 (2026-11-16)
        "summary": "BENJI의 배당 선언일 항목이 검토 필요로 판정됐다. 업그레이드(2025-05-23) 뒤 주말 지급이 관측됐다.",
        "reasons": [{"item": "배당 선언일 (주말·휴일 포함 여부)",
                     "reason": "문서는 NAV를 계산하는 날마다 배당을 선언한다고 적고 있고, 주말은 휴장일이다. "
                               "온체인에서는 업그레이드 뒤 주말 지급이 관측되어 사람의 확인이 필요하다."},
                    {"item": "보수", "reason": "보수가 문서와 다를 수 있음."}]}, ensure_ascii=False)


# ---------------- 3. 검증 ----------------
STOP = {"a", "an", "the", "of", "and", "or", "to", "in", "on", "at", "for", "by", "with", "its", "it", "is",
        "are", "be", "as", "that", "which", "from", "this", "these", "will", "when"}


def value_tokens(v):
    toks = [t.strip(".-") for t in re.findall(r"[a-z0-9$%][a-z0-9$%.\-]*", norm(v))]
    return [t for t in toks if t and t not in STOP and (len(t) > 1 or t.isdigit())]


def token_hits(value, text):
    """값의 핵심 단어 중 text에 있는 개수와 전체 개수. 띄어쓰기 차이("0.20 %")는 같은 것으로 본다."""
    toks = value_tokens(value)
    ev = norm(text)
    evc = ev.replace(" ", "")
    return sum(t in ev or t in evc for t in toks), len(toks)


def grounded(value, evidence, min_ratio=0.6):
    hit, n = token_hits(value, evidence)
    return n > 0 and hit / n >= min_ratio


def parse_terms(raw):
    d = json.loads(raw)
    bad = [f for f in FIELDS if not isinstance(d.get(f), dict) or "value" not in d[f]
           or not isinstance(d[f].get("evidence_ids"), list)]
    if bad:
        raise ValueError(f"스키마 불일치: {bad}")
    return d


def verify(terms, sid):
    out = {}
    for f in FIELDS:
        v, ids = terms[f]["value"], terms[f]["evidence_ids"]
        if v is None or (isinstance(v, str) and not v.strip()):
            out[f] = {"value": None, "evidence_ids": [], "status": "not_stated"}
            continue
        ids = [i for i in dict.fromkeys(ids) if isinstance(i, int)]
        # v2.1: 값의 핵심 단어가 하나도 없는 문장 번호는 근거에서 뺀다 (맞는 번호에 무관한 번호가 섞여 통과하던 문제)
        kept = [i for i in ids if i in sid and token_hits(v, sid[i])[0] > 0]
        if not ids:
            st = "rejected_no_evidence"
        elif any(i not in sid for i in ids):
            st = "rejected_unknown_id"
        elif not kept or not grounded(v, " ".join(sid[i] for i in kept)):
            st = "rejected_value_not_in_evidence"
        else:
            out[f] = {"value": v, "evidence_ids": kept, "dropped_ids": [i for i in ids if i not in kept],
                      "evidence_sents": [sid[i] for i in kept], "evidence": " ".join(sid[i] for i in kept),
                      "status": "verified"}
            continue
        out[f] = {"value": None, "evidence_ids": [], "status": st, "rejected_value": v, "rejected_ids": ids}
    return out


def canon(v):
    """다수결용 표기 정리: 대소문자·공백·앞 관사·끝 문장부호 차이는 같은 값."""
    return re.sub(r"^(a|an|the)\s+", "", norm(v)).strip(" .,;:")


def majority(runs):
    final = {}
    for f in FIELDS:
        stats = dict(Counter(r[f]["status"] for r in runs))
        ok = [r[f] for r in runs if r[f]["status"] == "verified"]
        if not ok:
            final[f] = {"value": None, "evidence": None, "evidence_ids": [], "agreement": 0.0, "statuses": stats}
            continue
        top, cnt = Counter(canon(x["value"]) for x in ok).most_common(1)[0]
        group = [x for x in ok if canon(x["value"]) == top]
        raw_top = Counter(x["value"] for x in group).most_common(1)[0][0]
        rep = next(x for x in group if x["value"] == raw_top)
        final[f] = {"value": raw_top, "evidence": rep["evidence"], "evidence_ids": rep["evidence_ids"],
                    "evidence_sents": rep["evidence_sents"], "agreement": round(cnt / len(runs), 2), "statuses": stats}
    return final


def number_guard(text, inputs_text):
    """LLM이 쓴 문장의 숫자가 입력에 있었는가. 1~10의 목록 번호는 제외."""
    src = inputs_text.replace(",", "")
    unknown = []
    for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        k = n.replace(",", "")
        if k.isdigit() and int(k) <= 10:
            continue
        if k not in src:
            unknown.append(n)
    return sorted(set(unknown))


STRONG = ["위반", "불법", "허위", "상충", "모순", "어긋", "매수", "매도"]
# v2.2: 단어 목록 대신 당위 어미 패턴. '해야 한다'만 넣었더니 '선언되어야 하므로'를 놓쳤다 (v2.1 실제 실행)
OUGHT = re.compile(r"[가-힣]+야\s?(?:하|한|합|함|할|했|된|됩|되)")


def tone_guard(text):
    """LLM 문장에 단정·당위 표현이 있는가. 판정은 이미 코드가 했으므로 리포트는 문서 사실과 관측된 차이만 말해야 한다."""
    hits = [w for w in STRONG if w in text] + [m.group(0) for m in OUGHT.finditer(text)]
    return list(dict.fromkeys(hits))


# ---------------- 4. 온체인 지표와 규칙 기반 판정 ----------------
def chain_metrics(fund):
    dv = pd.read_csv(CLEAN / f"{fund.lower()}_dividends.csv", parse_dates=["date_et"])
    ups = sorted({str(t)[:10] for t in pd.read_csv(ROOT / "검증" / "data" / f"{fund.lower()}_upgrades.csv")["ts_utc"]
                  if str(t) > "2024-11-01"})
    up = pd.Timestamp(ups[0])
    wk = lambda x: round(x["weekday_et"].isin(["Saturday", "Sunday"]).mean() * 100, 1)
    pre, post = dv[dv["date_et"] < up], dv[dv["date_et"] > up]
    return {"fund": fund, "chain": FUNDS[fund]["chain"],
            "dividend_record_period": f"{dv['date_et'].min():%Y-%m-%d} ~ {dv['date_et'].max():%Y-%m-%d}",
            "dividend_payments": int(len(dv)), "first_upgrade_in_operation": ups[0],
            "upgrades_in_operation": ups,
            "weekend_share_before_upgrade_pct": wk(pre), "payments_before_upgrade": int(len(pre)),
            "weekend_share_after_upgrade_pct": wk(post), "payments_after_upgrade": int(len(post)),
            "dividends_paid_as": "신규 토큰 발행(mint)"}


def has(term, *words):
    return term["value"] is not None and any(w in norm(term["evidence"]) for w in words)


def judge(terms, m):
    """판정과 추론은 코드가 한다. LLM은 근거 문장을 찾는 데까지만 관여한다."""
    rows = []
    timing, navd, closed = terms["dividend_declaration_timing"], terms["nav_calculation_days"], terms["fund_closed_days"]
    item = "배당 선언일 (주말·휴일 포함 여부)"
    chain = (f"업그레이드({m['first_upgrade_in_operation']}) 전 주말 지급 {m['weekend_share_before_upgrade_pct']}% "
             f"({m['payments_before_upgrade']}회) -> 후 {m['weekend_share_after_upgrade_pct']}% ({m['payments_after_upgrade']}회)")
    rule = ("문서: 배당은 NAV 계산일에 선언 + NAV는 NYSE·FRBNY가 여는 날에만 계산 + 주말 휴장 → 주말 선언 없음이 기대됨. "
            "온체인 주말 지급 > 0 → 검토 필요")
    if timing["value"] is None:
        rows.append({"item": item, "doc_quote": None, "chain": chain, "verdict": "문서에서 추출 실패", "rule": rule})
    else:
        facts = {"declaration_tied_to_nav": has(timing, "net asset value", "nav"),
                 "nav_only_on_open_days": has(navd, "open for business", "business day"),
                 "closed_on_weekends": has(closed, "weekend") or has(navd, "weekend")}
        quotes = list(timing["evidence_sents"])           # 문장마다 ' / '로 나눠 보이게 (v2.1까지는 이어 붙었다)
        if navd["value"] is not None:
            quotes += navd["evidence_sents"]
        quotes += [s for t in (closed, navd) if t["value"] is not None for s in t["evidence_sents"] if "weekend" in norm(s)]
        if all(facts.values()):
            verdict = "검토 필요" if m["weekend_share_after_upgrade_pct"] > 0 else "일치"
        else:
            verdict = "판정 보류 (문서 근거 부족)"
        rows.append({"item": item, "doc_quote": " / ".join(dict.fromkeys(quotes)), "chain": chain,
                     "verdict": verdict, "rule": rule, "doc_facts": facts})
    t = terms["dividend_payment_form"]
    if t["value"] is None:
        rows.append({"item": "배당 지급 형태", "doc_quote": None, "chain": f"배당 {m['dividend_payments']}회 모두 {m['dividends_paid_as']}",
                     "verdict": "문서에서 추출 실패", "rule": "문서가 추가 지분 지급 & 온체인이 토큰 발행 → 일치"})
    else:
        ok = "share" in str(t["value"]).lower()
        rows.append({"item": "배당 지급 형태", "doc_quote": t["evidence"], "chain": f"배당 {m['dividend_payments']}회 모두 {m['dividends_paid_as']}",
                     "verdict": "일치" if ok else "검토 필요", "rule": "문서가 추가 지분 지급 & 온체인이 토큰 발행 → 일치"})
    for f, label in [("expense_ratio", "보수"), ("share_price_target", "목표 주가")]:
        t = terms[f]
        rows.append({"item": label, "doc_quote": t["evidence"], "chain": "온체인 데이터로 확인할 수 없는 항목",
                     "verdict": "확인 불가" if t["value"] is not None else "문서에서 추출 실패", "rule": "온체인 대응 지표 없음"})
    return rows


# ---------------- 실행 ----------------
def run_dir(fund, step):
    d = LLM / "runs" / f"{datetime.now():%Y%m%d_%H%M%S}_{fund}_{step}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def finalize_extract(fund, d, results, sid, meta, result_name="result.json"):
    """검증된 실행 결과 → 다수결 → 규칙 판정 → 파일 저장. extract와 rescore가 같이 쓴다."""
    final = majority(results)
    st = Counter(r[f]["status"] for r in results for f in FIELDS)
    answered = sum(v for k, v in st.items() if k != "not_stated")
    out = {"fund": fund, "source": FUNDS[fund]["source"], "harness": HARNESS, **meta,
           "runs": len(results), "excerpt_chars": sum(map(len, sid.values())), "sentences": len(sid),
           "verified_rate": f"{st['verified']}/{answered}", "statuses": dict(st), "terms": final}
    (d / result_name).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (CLEAN / f"llm_terms_{fund.lower()}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    m = chain_metrics(fund)
    table = judge(final, m)
    (CLEAN / f"doc_vs_chain_auto_{fund.lower()}.json").write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[추출] 모델 {out['model']} | 문장 {len(sid)}개 {out['excerpt_chars']:,}자 | 실행 {len(results)}회 | "
          f"{out['seconds']}초 | 근거 검사 통과 {out['verified_rate']}")
    for f in FIELDS:
        r = final[f]
        print(f"  {f:28s} 값={str(r['value'])[:42]:42s} 근거=S{r['evidence_ids']} 일치율={r['agreement']:.2f} 상태={r['statuses']}")
    print(f"[판정] {len(table)}개 항목 -> " + ", ".join(f"{r['item']}:{r['verdict']}" for r in table))
    return out, table, m


def extract(fund, runs, dry):
    cfg = FUNDS[fund]
    source = cfg["doc"].read_text(encoding="utf-8")
    excerpt_text, sid = number_excerpts(retrieve(source))
    system, user = load_prompt("01_extract_terms.md")
    user = user.replace("{fund_name}", cfg["name"]).replace("{excerpts}", excerpt_text)
    schema = load_schema("terms.schema.json")
    d = run_dir(fund, "extract")
    (d / "prompt.txt").write_text(f"[SYSTEM]\n{system}\n\n[USER]\n{user}", encoding="utf-8")
    (d / "sentences.json").write_text(json.dumps(sid, ensure_ascii=False, indent=1), encoding="utf-8")
    results, t0 = [], time.time()
    for i in range(runs):
        for attempt in range(3):
            raw = call_mock("extract", i, sid) if dry else call_ollama(system, user, schema, temperature=0.0 if i == 0 else 0.3)
            (d / f"raw_{i + 1}_{attempt + 1}.json").write_text(raw, encoding="utf-8")
            try:
                results.append(verify(parse_terms(raw), sid))
                break
            except Exception as e:
                print(f"  실행 {i + 1} 재시도 {attempt + 1}: {e}")
    meta = {"model": "mock" if dry else env("OLLAMA_MODEL", DEFAULT_MODEL),
            "num_ctx": None if dry else int(env("OLLAMA_NUM_CTX", "16384")),
            "seconds": round(time.time() - t0, 1), "dry_run": dry, "run_dir": d.name}
    return finalize_extract(fund, d, results, sid, meta)


SECTIONS = [("검토 필요", "검토가 필요한 항목"), ("일치", "문서와 일치하는 항목"),
            ("확인 불가", "온체인으로 확인할 수 없는 항목")]


def assemble(fund, table, m, summary, reasons, model, unknown, tone, attempt_note=""):
    """리포트 뼈대는 코드가 만든다. LLM 문장은 요약과 '검토가 필요한 이유' 자리에만 들어간다."""
    q = lambda s: f'"{s}"' if s else "(문서에서 추출 실패)"
    L = [f"# {fund} 배당 점검 리포트", "",
         f"> 판정은 파이썬 규칙이 내렸다. 요약과 '검토가 필요한 이유'만 로컬 LLM({model})이 썼다.",
         f"> LLM 문장 검사 — 입력에 없는 숫자: {', '.join(unknown) if unknown else '없음'} / "
         f"단정·당위 표현: {', '.join(tone) if tone else '없음'}" + (f" / {attempt_note}" if attempt_note else ""), "",
         "## 요약", "", summary.strip(), ""]
    for verdict, title in SECTIONS:
        rows = [r for r in table if r["verdict"] == verdict]
        L += [f"## {title}", ""]
        if not rows:
            L += ["- 없음", ""]
            continue
        for r in rows:
            if verdict == "검토 필요":
                L += [f"### {r['item']}", "", f"- **문서 원문:** {q(r['doc_quote'])}", f"- **온체인 관측:** {r['chain']}",
                      f"- **판정 규칙:** {r['rule']}", f"- **검토가 필요한 이유:** {reasons.get(r['item'], '(LLM 설명 없음)')}", ""]
            elif verdict == "일치":
                L += [f"- **{r['item']}:** 문서 {q(r['doc_quote'])} / 온체인 {r['chain']}"]
            else:
                L += [f"- **{r['item']}:** 문서 {q(r['doc_quote'])} — {r['chain']}"]
        if verdict != "검토 필요":
            L += [""]
    rest = [r for r in table if r["verdict"] not in dict(SECTIONS)]
    if rest:
        L += ["## 판정 보류·추출 실패", ""] + [f"- **{r['item']}:** {r['verdict']}" for r in rest] + [""]
    L += ["## 데이터의 한계", "",
          f"- 블록체인: {m['chain']}만. 다른 체인에 발행된 물량과 장부 밖 보유분은 포함하지 않는다",
          f"- 배당 기록 기간: {m['dividend_record_period']} (배당 {m['dividend_payments']}회)",
          f"- 문서: {FUNDS[fund]['source']}",
          "- '검토 필요'는 위반 판단이 아니라 사람이 확인할 지점이라는 뜻이다", ""]
    return "\n".join(L)


def report_inputs(table, m):
    review = [r for r in table if r["verdict"] == "검토 필요"]
    review_in = [{k: r[k] for k in ("item", "doc_quote", "chain", "rule")} for r in review]
    all_in = [{"item": r["item"], "verdict": r["verdict"]} for r in table]
    return review, [json.dumps(x, ensure_ascii=False, indent=1) for x in (review_in, all_in, m)]


def parse_report(raw):
    p = json.loads(raw)
    assert isinstance(p.get("summary"), str) and isinstance(p.get("reasons"), list), "summary/reasons 형식 아님"
    return p


def check_report(parsed, review, inputs_text):
    """LLM 리포트 문장 검사: 검토 필요 항목의 이유만 남기고, 숫자·표현 검사를 돌린다."""
    names = {r["item"] for r in review}
    reasons = {x["item"]: x["reason"] for x in parsed["reasons"]
               if isinstance(x, dict) and x.get("item") in names and isinstance(x.get("reason"), str)}
    dropped = [x.get("item") for x in parsed["reasons"] if isinstance(x, dict) and x.get("item") not in names]
    llm_text = parsed["summary"] + " " + " ".join(reasons.values())
    return reasons, dropped, llm_text, number_guard(llm_text, inputs_text), tone_guard(llm_text)


def finish_report(fund, table, m, parsed, model, d, note, secs=None, out_name="report.md", attempt_note=""):
    """LLM 응답(JSON) → 검사 → 코드가 만든 뼈대에 끼워 리포트 저장. report와 rescore가 같이 쓴다."""
    review, (rj, aj, mj) = report_inputs(table, m)
    reasons, dropped, llm_text, unknown, tone = check_report(parsed, review, rj + aj + mj)
    md = assemble(fund, table, m, parsed["summary"], reasons, model, unknown, tone, attempt_note)
    REPORTS.mkdir(exist_ok=True)
    header = (f"<!-- 생성: {datetime.now():%Y-%m-%d %H:%M} | harness {HARNESS} | {note} | 모델: {model} | "
              f"입력에 없는 숫자: {unknown or '없음'} | 단정·당위 표현: {tone or '없음'}"
              + (f" | {attempt_note}" if attempt_note else "") + " -->\n")
    (REPORTS / f"{fund.lower()}_report.md").write_text(header + md, encoding="utf-8")
    (d / out_name).write_text(header + md, encoding="utf-8")
    print(f"[리포트] {secs if secs is not None else '-'}초 | LLM 문장 {len(llm_text)}자 | 입력에 없는 숫자 {unknown or '없음'} | "
          f"단정·당위 표현 {tone or '없음'} | 검토 필요 {len(review)}개 중 이유 {len(reasons)}개 | 버린 항목 {dropped or '없음'}"
          + (f" | {attempt_note}" if attempt_note else ""))
    return md, unknown, tone


REPORT_ATTEMPTS = 3
FEEDBACK = ("앞 답변에 다음 문제가 있다: {problems}. 판정은 바꾸지 말고 같은 JSON 형식으로 다시 써라. "
            "문서 내용은 '문서는 …라고 적고 있다'처럼 문서에 적힌 그대로 옮기고, 온체인에서 관측된 차이만 쓴다. "
            "'~해야 한다', '~되어야 한다' 같은 당위 표현, '상충'·'모순' 같은 강한 표현, 입력에 없는 숫자는 쓰지 않는다.")


def attempt_summary(attempts):
    if len(attempts) <= 1:
        return ""
    bad = [f"{a['attempt']}회차 " + ", ".join(x for x in (f"숫자 {a['unknown_numbers']}" if a["unknown_numbers"] else "",
                                                          f"표현 {a['tone']}" if a["tone"] else "") if x)
           for a in attempts if a["unknown_numbers"] or a["tone"]]
    return f"작성 {len(attempts)}회 (피드백 재시도: " + "; ".join(bad) + ")"


def report(fund, dry, table=None, m=None):
    if table is None:
        table = json.loads((CLEAN / f"doc_vs_chain_auto_{fund.lower()}.json").read_text(encoding="utf-8"))
        m = chain_metrics(fund)
    review, (rj, aj, mj) = report_inputs(table, m)
    system, user = load_prompt("02_write_report.md")
    user = (user.replace("{fund_name}", fund).replace("{review_items_json}", rj)
            .replace("{all_items_json}", aj).replace("{metrics_json}", mj))
    d = run_dir(fund, "report")
    (d / "prompt.txt").write_text(f"[SYSTEM]\n{system}\n\n[USER]\n{user}", encoding="utf-8")
    t0, history, attempts, best = time.time(), [], [], None
    # v2.2 피드백 재시도: 숫자·표현 검사에 걸리면 걸린 내용을 알려 주고 같은 대화에서 다시 쓰게 한다 (최대 3회)
    for attempt in range(REPORT_ATTEMPTS):
        raw = call_mock("report", attempt) if dry else call_ollama(
            system, user, load_schema("report.schema.json"), temperature=0.2, history=history)
        (d / f"report_raw_{attempt + 1}.json").write_text(raw, encoding="utf-8")
        try:
            parsed = parse_report(raw)
        except Exception as e:
            print(f"  리포트 {attempt + 1}회차 형식 오류: {e}")
            attempts.append({"attempt": attempt + 1, "format_error": str(e), "unknown_numbers": [], "tone": []})
            continue
        _, _, _, unknown, tone = check_report(parsed, review, rj + aj + mj)
        attempts.append({"attempt": attempt + 1, "unknown_numbers": unknown, "tone": tone})
        score = len(unknown) + len(tone)
        if best is None or score <= best[0]:
            best = (score, parsed)
        if score == 0:
            break
        problems = ", ".join(x for x in (f"입력에 없는 숫자 {unknown}" if unknown else "",
                                         f"쓰면 안 되는 표현 {tone}" if tone else "") if x)
        print(f"  리포트 {attempt + 1}회차 검사 실패 ({problems}) → 피드백 재시도")
        history += [{"role": "assistant", "content": raw}, {"role": "user", "content": FEEDBACK.format(problems=problems)}]
    parsed = best[1] if best else {"summary": "(LLM 응답 형식 오류)", "reasons": []}
    (d / "report_attempts.json").write_text(json.dumps(attempts, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "report_final.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=1), encoding="utf-8")
    model = "mock" if dry else env("OLLAMA_MODEL", DEFAULT_MODEL)
    return finish_report(fund, table, m, parsed, model, d, f"dry_run={dry}", round(time.time() - t0, 1),
                         attempt_note=attempt_summary(attempts))


def first_parsed(d, pattern, parse):
    """저장된 원응답에서 실행마다 처음으로 형식 검사를 통과한 응답을 고른다 (실행 때와 같은 규칙)."""
    by_run = {}
    for f in sorted(d.glob(pattern), key=lambda p: [int(x) for x in re.findall(r"\d+", p.stem)]):
        k = tuple(int(x) for x in re.findall(r"\d+", f.stem)[:-1])
        if k in by_run:
            continue
        try:
            by_run[k] = parse(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return [by_run[k] for k in sorted(by_run)]


def rescore(fund, extract_run, report_run=None):
    """LLM을 다시 부르지 않고, 저장된 원응답을 지금 코드의 검사·판정으로 다시 채점한다.
    모델 선택이나 검사 규칙을 바꿨을 때 GPU 없이 결과 파일을 다시 만들 수 있다."""
    d = LLM / "runs" / extract_run
    sid = {int(k): v for k, v in json.loads((d / "sentences.json").read_text(encoding="utf-8")).items()}
    prev = json.loads((d / "result.json").read_text(encoding="utf-8"))
    results = [verify(t, sid) for t in first_parsed(d, "raw_*_*.json", parse_terms)]
    meta = {k: prev.get(k) for k in ("model", "num_ctx", "seconds", "dry_run")}
    meta.update({"run_dir": extract_run, "rescored_at": f"{datetime.now():%Y-%m-%d %H:%M}",
                 "rescored_from": prev.get("harness")})
    out, table, m = finalize_extract(fund, d, results, sid, meta, result_name="result_rescored.json")
    if report_run:
        rd = LLM / "runs" / report_run
        if (rd / "report_final.json").exists():   # v2.2 이후: 피드백 재시도 끝에 고른 응답
            parsed = json.loads((rd / "report_final.json").read_text(encoding="utf-8"))
            attempts = json.loads((rd / "report_attempts.json").read_text(encoding="utf-8"))
        else:                                      # v2.1까지: 첫 응답
            parsed = (first_parsed(rd, "report_raw_*.json", parse_report) or [{"summary": "(LLM 응답 형식 오류)", "reasons": []}])[0]
            attempts = []
        finish_report(fund, table, m, parsed, out["model"], rd, f"재채점(원응답 {report_run})", out_name="report_rescored.md",
                      attempt_note=attempt_summary(attempts))
    return out, table, m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["extract", "report", "all", "rescore"])
    ap.add_argument("--fund", default="BENJI", choices=list(FUNDS))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--extract-run", help="rescore: 다시 채점할 추출 실행 폴더 이름 (llm/runs/ 아래)")
    ap.add_argument("--report-run", help="rescore: 리포트 문장을 가져올 리포트 실행 폴더 이름")
    a = ap.parse_args()
    if a.step == "rescore":
        if not a.extract_run:
            ap.error("rescore에는 --extract-run이 필요하다")
        rescore(a.fund, a.extract_run, a.report_run)
    else:
        if a.step in ("extract", "all"):
            _, tb, mt = extract(a.fund, a.runs, a.dry_run)
        if a.step in ("report", "all"):
            report(a.fund, a.dry_run, *(() if a.step == "report" else (tb, mt)))
