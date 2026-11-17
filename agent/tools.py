# -*- coding: utf-8 -*-
"""두 스택이 같이 쓰는 결정론적 도구 함수 (실제 BENJI 데이터 사용). 숫자는 전부 코드가 계산한다."""
import json, os, re
from pathlib import Path
import pandas as pd

def _data_dir() -> Path:
    """데이터 폴더. 환경변수 STO_DATA_DIR이 있으면 그것, 없으면 저장소 안의 검증/data (agent/ 바로 위)."""
    return Path(os.environ.get("STO_DATA_DIR") or Path(__file__).resolve().parents[1] / "검증" / "data")


def _div():
    return pd.read_csv(_data_dir() / "clean" / "benji_dividends.csv", parse_dates=["date_et"])


def _first_upgrade():
    ts = pd.read_csv(_data_dir() / "benji_upgrades.csv")["ts_utc"]
    return sorted({str(t)[:10] for t in ts if str(t) > "2024-11-01"})[0]


def weekend_profile() -> dict:
    """BENJI 배당의 업그레이드 전후 주말 지급 비율 (조사 에이전트용)."""
    dv, up = _div(), pd.Timestamp(_first_upgrade())
    wk = lambda x: float(round(x["weekday_et"].isin(["Saturday", "Sunday"]).mean() * 100, 1))
    pre, post = dv[dv["date_et"] < up], dv[dv["date_et"] > up]
    return {"upgrade_date": str(up.date()), "before_pct": wk(pre), "before_n": int(len(pre)),
            "after_pct": wk(post), "after_n": int(len(post)), "total_n": int(len(dv))}


def detect_change_point() -> dict:
    """주말 배당이 처음 나온 날과 가장 가까운 업그레이드 날짜."""
    dv = _div()
    wkd = dv[dv["weekday_et"].isin(["Saturday", "Sunday"])]
    first = str(wkd["date_et"].min().date()) if len(wkd) else None
    return {"first_weekend_dividend": first, "nearest_upgrade": _first_upgrade()}


def upgrade_events(start: str = "2025-05-20", end: str = "2025-05-26") -> dict:
    """기간 안의 ERC1967 Upgraded 이벤트."""
    ev = pd.read_csv(_data_dir() / "benji_upgrades.csv")
    sel = ev[(ev["ts_utc"] >= start) & (ev["ts_utc"] <= end + "T23:59:59Z")]
    return {"count": int(len(sel)), "timestamps": sel["ts_utc"].tolist()}


def recompute_weekend() -> dict:
    """검증 에이전트용: 요일 열을 쓰지 않고 날짜에서 요일을 다시 계산하는 별도 구현."""
    dv, up = _div(), pd.Timestamp(_first_upgrade())
    isw = dv["date_et"].dt.day_of_week >= 5
    b, a = dv["date_et"] < up, dv["date_et"] > up
    return {"before_pct": float(round(isw[b].mean() * 100, 1)), "after_pct": float(round(isw[a].mean() * 100, 1)),
            "before_n": int(b.sum()), "after_n": int(a.sum())}


def check_citations(claim: str, evidence_json: str) -> dict:
    """감사 에이전트용: 주장에 나온 숫자가 모두 도구 결과에 있는가."""
    src = evidence_json.replace(",", "")
    nums = [n for n in re.findall(r"\d+(?:\.\d+)?", claim.replace(",", "")) if not (n.isdigit() and int(n) <= 10)]
    missing = sorted({n for n in nums if n not in src})
    return {"numbers": len(nums), "missing": missing, "pass": not missing}


def redemption_events(after: str = "2026-10-31") -> dict:
    """기간 이후 BENJI 환매(소각) 건수와 합계, 날짜 (전처리된 흐름 기준)."""
    f = pd.read_csv(_data_dir() / "clean" / "benji_flows.csv", parse_dates=["date_et"])
    r = f[(f["class"] == "redemption") & (f["date_et"] > after)]
    return {"count": int(len(r)), "total_usd": float(round(r["amount"].sum(), 2)),
            "dates": sorted({str(d.date()) for d in r["date_et"]})}


def recompute_burn(after: str = "2026-10-31") -> dict:
    """검증 에이전트용: 전처리 결과가 아니라 원본 이동 기록의 소각 합계로 다시 계산."""
    t = pd.read_csv(_data_dir() / "benji_transfers.csv")
    b = t[(t["type"] == "token_burning") & (t["timestamp"] > after + "T23:59:59")]
    return {"count": int(len(b)), "total_usd": float(round(b["amount"].sum(), 2))}


def bridge_events() -> dict:
    """BENJI 체인 이동(브리지) 흐름 건수. 체인 이동 가설 검증용."""
    f = pd.read_csv(_data_dir() / "clean" / "benji_flows.csv")
    n = int(f["class"].isin(["bridge_in", "bridge_out"]).sum())
    return {"bridge_flows": n, "classes": sorted(f["class"].unique().tolist())}


def prospectus_search(query: str) -> dict:
    """투자설명서(SEC 485BPOS 2026-08-01) 원문에서 검색어가 들어간 문장 최대 2개."""
    txt = (_data_dir() / "docs" / "benji_485bpos_2026-08-01.txt").read_text(encoding="utf-8")
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", txt)
    q = [w.lower() for w in query.split()]
    scored = sorted(((sum(w in s.lower() for w in q), i) for i, s in enumerate(sents)), reverse=True)
    hits = [{"sentence_no": i, "text": sents[i][:300]} for sc, i in scored[:2] if sc > 0]
    return {"query": query, "hits": hits}


if __name__ == "__main__":
    for f in (weekend_profile, detect_change_point, upgrade_events, recompute_weekend, redemption_events, recompute_burn, bridge_events):
        print(f.__name__, json.dumps(f(), ensure_ascii=False))
    print(json.dumps(prospectus_search("declare dividends net asset value calculation"), ensure_ascii=False)[:400])
