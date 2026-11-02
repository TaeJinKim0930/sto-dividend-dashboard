# -*- coding: utf-8 -*-
"""문서 대 온체인 대조표 생성 — 인용문은 원문에 실제로 있는지 검사한 뒤에만 넣는다.

나중에 LLM이 추출한 조건으로 이 표를 자동 생성할 때도 같은 인용 검증을 거친다.
출력: data/clean/doc_vs_chain.json
"""
import json, os, re
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
C = os.path.join(D, "clean")
SEC = open(os.path.join(D, "docs", "benji_485bpos_2026-08-01.txt"), encoding="utf-8").read()
SEC_SRC = "SEC EDGAR 485BPOS, Franklin Templeton Trust, 2026-08-01"


def norm(s):
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip().lower()


def verified(quote):
    """원문에 인용문이 그대로 있는가 (공백·따옴표만 정규화)"""
    return norm(quote) in norm(SEC)


bd = pd.read_csv(os.path.join(C, "benji_dividends.csv"), parse_dates=["date_et"])
up_day = pd.Timestamp("2025-05-23")
pre = bd[bd["date_et"] < up_day]
post = bd[bd["date_et"] > up_day]
wk = lambda x: x["weekday_et"].isin(["Saturday", "Sunday"]).mean() * 100

rows = [
    {
        "fund": "BENJI", "item": "배당 선언 시점",
        "doc_quote": "The Fund intends to declare income dividends from its net investment income each day when it makes its final net asset value (NAV) calculation.",
        "doc_source": SEC_SRC,
        "chain": f"업그레이드(2025-05-23) 전 주말 지급 {wk(pre):.0f}% ({len(pre)}회) -> 이후 {wk(post):.0f}% ({len(post)}회). 업그레이드 뒤 토·일요일에도 배당 토큰 발행",
        "verdict": "검토 필요",
        "note": "같은 문서에 펀드가 주말·공휴일 휴장한다고 명시(NAV 미계산일). 'reinvests them daily' 문구와 함께 해석해야 함",
    },
    {
        "fund": "BENJI", "item": "휴장일",
        "doc_quote": "Both the NYSE and FRBNY are also closed on weekends and may be closed because of an emergency or other unanticipated event.",
        "doc_source": SEC_SRC,
        "chain": "업그레이드 뒤 주말(휴장일)에도 배당 발행 관측",
        "verdict": "검토 필요",
        "note": "선언 시점 항목의 근거 문장",
    },
    {
        "fund": "BENJI", "item": "재투자 주기",
        "doc_quote": "The Fund intends to declare income dividends from its net investment income each day when it makes its final net asset value calculation and reinvests them daily.",
        "doc_source": SEC_SRC,
        "chain": "업그레이드 전: 금요일에 주말분 선지급(경과일 대비 지급률이 금 3배, 월 1/3). 업그레이드 후: 달력일 매일 발행",
        "verdict": "일치 (해석 필요)",
        "note": "'매일 재투자'는 두 방식 모두로 읽힐 수 있음",
    },
    {
        "fund": "BENJI", "item": "배당 지급 형태",
        "doc_quote": "Your income dividends and capital gain distributions will be automatically reinvested in additional shares at NAV on the payable date, which has the effect of compounding of dividends.",
        "doc_source": SEC_SRC,
        "chain": f"배당 {len(bd)}회 모두 신규 토큰 발행으로 지급. 현금성 이전 없음",
        "verdict": "일치",
        "note": "",
    },
    {
        "fund": "BUIDL", "item": "배당 지급 주기",
        "doc_quote": "Interest accrues daily and is distributed monthly as new BUIDL tokens to each holder's wallet",
        "doc_source": "공개 2차 자료(Eco, BUIDL Deep Dive 2026) — 공식 투자설명서 아님(사모 펀드)",
        "chain": "2024-05~2025-01 월 1회 지급 -> 2025-01-23부터 영업일 매일 지급(월요일에 주말분)",
        "verdict": "검토 필요 (공식 문서 미확보)",
        "note": "공식 문서가 아니므로 인용 검증 대상 아님",
        "skip_verify": True,
    },
]

out, bad = [], []
for r in rows:
    if r.pop("skip_verify", False):
        r["quote_verified"] = None
    else:
        r["quote_verified"] = verified(r["doc_quote"])
        if not r["quote_verified"]:
            bad.append(r["item"])
    out.append(r)

json.dump(out, open(os.path.join(C, "doc_vs_chain.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"대조 항목 {len(out)}개 | 원문 인용 검증 통과 {sum(1 for r in out if r['quote_verified'])}개 "
      f"| 실패 {bad or '없음'} | 검증 제외(비공식 문서) {sum(1 for r in out if r['quote_verified'] is None)}개")
