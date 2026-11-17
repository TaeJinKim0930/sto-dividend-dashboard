# -*- coding: utf-8 -*-
"""토큰화 펀드 배당 검증 대시보드 (Streamlit).

실행: python -m streamlit run dashboard/app.py
데이터: 검증/data/clean/ (07_preprocess.py, 08_analyze.py, 10_doc_vs_chain.py 산출물)
      AI 점검 리포트 탭: llm/harness.py 산출물 (llm_terms_benji.json, doc_vs_chain_auto_benji.json, reports/benji_report.md, llm/runs/)
"""
import io
import json
import os
import re
import urllib.request
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "검증" / "data" / "clean"
RAW = ROOT / "검증" / "data"
ZERO = "0x0000000000000000000000000000000000000000"
DUST = 1e-6
COLOR = {"BUIDL": "#8B1A1A", "BENJI": "#2F5D8A"}
CLASS_KO = {"subscription": "신규 청약", "dividend": "배당", "swap_in": "클래스 전환 유입",
            "bridge_in": "체인 유입", "redemption": "상환", "swap_out": "클래스 전환 유출",
            "bridge_out": "체인 이동", "transfer": "지갑 간 이전"}
FIELD_KO = {"dividend_declaration_timing": "배당 선언 시점", "nav_calculation_days": "NAV 계산일",
            "dividend_payment_form": "배당 지급 형태", "reinvestment_frequency": "재투자 주기",
            "fund_closed_days": "휴장일", "share_price_target": "목표 기준가", "expense_ratio": "보수율",
            "official_record": "공식 소유 기록"}
DAY_KO = {"Monday": "월", "Tuesday": "화", "Wednesday": "수", "Thursday": "목",
          "Friday": "금", "Saturday": "토", "Sunday": "일"}

st.set_page_config(page_title="토큰화 펀드 배당 검증", layout="wide")


def balances(fl):
    inflow = fl[fl["dst"] != ZERO].groupby("dst")["amount"].sum()
    outflow = fl[fl["src"] != ZERO].groupby("src")["amount"].sum()
    bal = inflow.sub(outflow, fill_value=0)
    return bal[bal > DUST].sort_values(ascending=False)


def data_signature():
    """데이터 파일이 바뀌면(재수집·GitHub 반영) 캐시를 새로 만들도록 파일 크기·수정 시각을 키로 쓴다."""
    files = sorted(CLEAN.glob("*.*")) + [RAW / "benji_upgrades.csv", ROOT / "reports" / "benji_report.md"]
    return tuple((f.name, f.stat().st_size, int(f.stat().st_mtime)) for f in files if f.exists())


@st.cache_data
def load(sig):
    data = {}
    for f in ("buidl", "benji"):
        name = f.upper()
        fl = pd.read_csv(CLEAN / f"{f}_flows.csv", parse_dates=["date_et"])
        dv = pd.read_csv(CLEAN / f"{f}_dividends.csv", parse_dates=["date_et"])
        mo = pd.read_csv(CLEAN / f"{f}_monthly.csv")
        wa = pd.read_csv(CLEAN / f"{f}_wallets.csv")
        data[name] = {"flows": fl, "div": dv, "monthly": mo, "wallets": wa, "bal": balances(fl)}
    data["upgrades"] = {
        "BUIDL": [],  # ProxyTargetSet 1회는 배포 시점(2024-03-01) 최초 설정
        "BENJI": sorted({str(d)[:10] for d in pd.read_csv(RAW / "benji_upgrades.csv")["ts_utc"]
                         if str(d) > "2024-11-01"}),
    }
    data["doc"] = json.loads((CLEAN / "doc_vs_chain.json").read_text(encoding="utf-8"))
    data["ai"] = load_ai()
    return data


def md_safe(s):
    """Streamlit 마크다운은 $...$를 수식으로 바꾼다 ("$1.00 ... $1.00" → 수식). 달러 기호를 글자로 남긴다."""
    return s.replace("$", "\\$")


def load_ai():
    """로컬 LLM 하네스 결과. 없으면 None (GPU 컴퓨터에서 llm/harness.py를 돌리면 생긴다)."""
    try:
        terms = json.loads((CLEAN / "llm_terms_benji.json").read_text(encoding="utf-8"))
        table = json.loads((CLEAN / "doc_vs_chain_auto_benji.json").read_text(encoding="utf-8"))
        rep = (ROOT / "reports" / "benji_report.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    comp = {}   # 모델별 가장 최근 v2 이상 실제 실행 (재채점 결과가 있으면 그것)
    for d in sorted((ROOT / "llm" / "runs").glob("*_BENJI_extract")):
        f = d / "result_rescored.json" if (d / "result_rescored.json").exists() else d / "result.json"
        if not f.exists():
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        if r.get("dry_run") or not str(r.get("harness", "")).startswith("v2"):
            continue
        t = r["terms"]
        comp[r["model"]] = {"모델": r["model"], "추출 5회(초)": r["seconds"], "근거 검사 통과": r["verified_rate"],
                            "값이 나온 항목": f"{sum(v['value'] is not None for v in t.values())}/{len(t)}",
                            "평균 일치율": round(sum(v["agreement"] for v in t.values()) / len(t), 3),
                            "실행 폴더": d.name}
    return {"terms": terms, "table": table, "report": rep, "comp": list(comp.values())}


SIG = data_signature()
D = load(SIG)
FUNDS = ["BUIDL", "BENJI"]


@st.cache_data
def excel_bytes(f, classes, start, end, sig):
    """필터 조합별로 한 번만 만든다 (매 화면 갱신마다 13,000건 Excel을 다시 쓰지 않도록)"""
    fl = D[f]["flows"]
    rev = {v: k for k, v in CLASS_KO.items()}
    sel = fl[fl["class"].isin([rev[c] for c in classes])
             & (fl["date_et"].dt.date >= start) & (fl["date_et"].dt.date <= end)].copy()
    sel["구분"] = sel["class"].map(CLASS_KO)
    view = sel[["ts_kst", "date_et", "구분", "fn", "src", "dst", "amount", "tx_hash"]]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        view.assign(date_et=view["date_et"].dt.date).to_excel(w, index=False, sheet_name=f"{f}_거래")
        D[f]["monthly"].to_excel(w, index=False, sheet_name=f"{f}_월별")
    return buf.getvalue()

# ---------------- 머리말 ----------------
st.title("토큰화 펀드 배당 검증 대시보드")
last = max(D[f]["flows"]["date_et"].max() for f in FUNDS).date()
st.caption(f"투자설명서에 적힌 배당 조건과 블록체인에 남은 실제 지급 기록을 대조합니다 · "
           f"대상: BlackRock BUIDL, Franklin Templeton BENJI (Ethereum) · 데이터 기준일 {last} · "
           "출처: Blockscout API, Etherscan API, SEC EDGAR")

cols = st.columns(len(FUNDS))
for col, f in zip(cols, FUNDS):
    fl, dv = D[f]["flows"], D[f]["div"]
    bal = D[f]["bal"]
    recent = dv[dv["date_et"] >= dv["date_et"].max() - pd.Timedelta(days=30)]["annual_pct"].median()
    with col:
        st.subheader(f)
        a, b, c, d = st.columns(4)
        a.metric("현재 잔고", f"${bal.sum() / 1e6:,.1f}M")
        b.metric("보유 지갑", f"{len(bal)}개")
        c.metric("누적 배당", f"${fl.loc[fl['class'] == 'dividend', 'amount'].sum() / 1e6:,.2f}M")
        d.metric("최근 30일 지급률(연)", f"{recent:.2f}%")
        st.caption(f"운영 중 컨트랙트 업그레이드 {len(D['upgrades'][f])}회"
                   + (f" ({', '.join(D['upgrades'][f])})" if D["upgrades"][f] else ""))

tabs = st.tabs(["배당 지급률", "자금 흐름", "지급 요일", "문서 대 온체인", "AI 점검 리포트", "이상 탐지", "원천 데이터",
                "AI 감사 관제실"])

# ---------------- 1. 배당 지급률 ----------------
with tabs[0]:
    st.markdown("배당 1회 금액을 **직전 지급일과의 경과일로 나눠** 1일 지급률로 맞춘 뒤 연율로 환산했습니다. "
                "월요일에 주말 사흘 치를 몰아 주는 효과가 사라집니다.")
    show_raw = st.checkbox("정규화 전 값도 보기 (BUIDL)", value=False)
    fig = go.Figure()
    if show_raw:
        r = D["BUIDL"]["div"].dropna(subset=["daily_rate"])
        fig.add_trace(go.Scatter(x=r["date_et"], y=r["med_ratio"] * 365 * 100, mode="markers",
                                 marker=dict(size=4, color="#B0B0B0"), name="BUIDL 정규화 전"))
    for f in FUNDS:
        r = D[f]["div"].dropna(subset=["daily_rate"])
        fig.add_trace(go.Scatter(x=r["date_et"], y=r["annual_pct"], mode="lines",
                                 line=dict(color=COLOR[f], width=2), name=f"{f} 정규화 후"))
    fig.add_vline(x="2025-01-23", line_dash="dash", line_color="#666")
    fig.add_annotation(x="2025-01-23", y=1, yref="paper", text="BUIDL 월배당 → 매일 배당", showarrow=False,
                       xanchor="left", font=dict(size=11, color="#555"))
    for u in D["upgrades"]["BENJI"]:
        fig.add_vline(x=u, line_dash="dot", line_color=COLOR["BENJI"])
    fig.update_layout(height=430, yaxis_title="연율 환산 지급률 (%)", yaxis_range=[0, 20 if show_raw else 8],
                      legend=dict(orientation="h", y=-0.15), margin=dict(t=20))
    st.plotly_chart(fig, width="stretch")
    st.caption("점선(파랑) = BENJI 컨트랙트 업그레이드일. BENJI는 업그레이드 전 금요일에 주말분을 미리 지급해 "
               "경과일 정규화 후에도 오르내림이 남습니다 (펀드 간 비교는 주 단위 합산이 안전).")

# ---------------- 2. 자금 흐름 ----------------
with tabs[1]:
    f = st.radio("펀드", FUNDS, horizontal=True, key="flow_fund")
    mo = D[f]["monthly"].copy()
    mo["month"] = pd.to_datetime(mo["month"])
    longs = []
    for k, sign in [("subscription", 1), ("swap_in", 1), ("bridge_in", 1),
                    ("redemption", -1), ("swap_out", -1), ("bridge_out", -1)]:
        if k in mo:
            longs.append(pd.DataFrame({"월": mo["month"], "구분": CLASS_KO[k], "금액(백만 달러)": sign * mo[k] / 1e6}))
    lf = pd.concat(longs)
    fig = px.bar(lf, x="월", y="금액(백만 달러)", color="구분", barmode="relative",
                 color_discrete_map={"신규 청약": "#2F5D8A", "클래스 전환 유입": "#E8C35A", "체인 유입": "#C9C9C9",
                                     "상환": "#8B1A1A", "클래스 전환 유출": "#D4A017", "체인 이동": "#9A9A9A"})
    fig.add_trace(go.Scatter(x=mo["month"], y=mo["supply_end"] / 1e6, name="월말 잔고", yaxis="y2",
                             line=dict(color="black", width=2)))
    fig.update_layout(height=450, yaxis2=dict(overlaying="y", side="right", title="월말 잔고(백만 달러)"),
                      legend=dict(orientation="h", y=-0.2), margin=dict(t=20))
    st.plotly_chart(fig, width="stretch")
    tot = D[f]["flows"].groupby("class")["amount"].sum()
    burns = tot.reindex(["redemption", "swap_out", "bridge_out"]).fillna(0)
    if burns.sum() > 0:
        st.info(f"{f} 소각 {burns.sum() / 1e6:,.0f}백만 달러 중 실제 상환은 {burns['redemption'] / burns.sum() * 100:.1f}%입니다. "
                "나머지는 다른 클래스로의 전환과 다른 체인으로의 이동이라, 사유 로그로 분리하지 않으면 상환액이 부풀려집니다.")

# ---------------- 3. 지급 요일 ----------------
with tabs[2]:
    rows = []
    b = D["BUIDL"]["div"]
    for d, n in b[b["era"] == "daily"]["weekday_et"].value_counts().items():
        rows.append({"요일": DAY_KO[d], "구분": "BUIDL (매일 배당기)", "지급 횟수": n})
    j = D["BENJI"]["div"]
    up = pd.Timestamp(D["upgrades"]["BENJI"][0]) if D["upgrades"]["BENJI"] else j["date_et"].max()
    for lab, seg in [("BENJI 업그레이드 전", j[j["date_et"] < up]), ("BENJI 업그레이드 후", j[j["date_et"] > up])]:
        for d, n in seg["weekday_et"].value_counts().items():
            rows.append({"요일": DAY_KO[d], "구분": lab, "지급 횟수": n})
    wf = pd.DataFrame(rows)
    fig = px.bar(wf, x="요일", y="지급 횟수", color="구분", barmode="group",
                 category_orders={"요일": list(DAY_KO.values())},
                 color_discrete_sequence=["#8B1A1A", "#9DB4CC", "#2F5D8A"])
    fig.update_layout(height=420, legend=dict(orientation="h", y=-0.15), margin=dict(t=20))
    st.plotly_chart(fig, width="stretch")
    pre, post = j[j["date_et"] < up], j[j["date_et"] > up]
    wk = lambda x: x["weekday_et"].isin(["Saturday", "Sunday"]).mean() * 100
    st.warning(f"BENJI는 {up.date()} 컨트랙트 업그레이드 전 주말 지급이 {wk(pre):.0f}%였고, 업그레이드 후 {wk(post):.0f}%입니다. "
               "코드 업그레이드와 배당 운영 방식 변경이 같은 날 일어났습니다.")

# ---------------- 4. 문서 대 온체인 ----------------
with tabs[3]:
    st.markdown("투자설명서 원문 문장과 온체인 관측을 나란히 놓았습니다. 인용문은 **원문에 실제로 있는지 코드로 검사한 문장만** 넣습니다. "
                "판정은 위반 여부가 아니라 **사람이 검토할 지점**을 표시합니다.")
    badge = {"일치": "🟢", "일치 (해석 필요)": "🟡", "검토 필요": "🟠", "검토 필요 (공식 문서 미확보)": "⚪"}
    for r in D["doc"]:
        with st.container(border=True):
            h1, h2 = st.columns([3, 1])
            h1.markdown(f"**{r['fund']} · {r['item']}**")
            h2.markdown(f"{badge.get(r['verdict'], '⚪')} **{r['verdict']}**")
            c1, c2 = st.columns(2)
            v = r.get("quote_verified")
            mark = "원문 인용 검증됨 ✓" if v else ("검증 대상 아님(비공식 자료)" if v is None else "원문 불일치 ✗")
            c1.markdown(f"**문서**\n\n> {r['doc_quote']}\n\n<small>{r['doc_source']} · {mark}</small>",
                        unsafe_allow_html=True)
            c2.markdown(f"**온체인 관측**\n\n{r['chain']}")
            if r.get("note"):
                st.caption(r["note"])
    st.caption("위 대조표는 사람이 원문을 확인해 만든 기준표입니다. 생성형 AI가 같은 대조를 자동으로 한 결과는 'AI 점검 리포트' 탭에 있습니다.")

# ---------------- 5. AI 점검 리포트 ----------------
with tabs[4]:
    ai = D["ai"]
    if ai is None:
        st.info("아직 AI 결과가 없습니다. GPU 컴퓨터에서 `python llm/harness.py all --fund BENJI --runs 5`를 실행하세요.")
    else:
        t = ai["terms"]
        st.markdown(f"로컬 LLM(**{t['model']}**)이 BENJI 투자설명서 41만 자에서 조건이 적힌 문장을 **번호로 가리키고**, "
                    "판정은 **파이썬 규칙**이 내립니다. LLM 출력은 근거 검사·다수결·숫자 검사를 통과해야 채택합니다.")
        # AI 결과가 지금 데이터로 만든 것인지: 리포트의 BENJI 배당 기록 끝 날짜와 지금 데이터의 BENJI 마지막 배당일을 비교
        # (거래 기준일과 비교하면 배당이 하루 늦게 찍히는 날마다 오래된 결과로 잘못 표시된다 — 2026-11-16 수정)
        period = re.search(r"배당 기록 기간: \S+ ~ (\S+)", ai["report"])
        benji_last_div = D["BENJI"]["div"]["date_et"].max().date()
        if period and str(period.group(1)) != str(benji_last_div):
            st.caption(f"AI 점검은 BENJI 배당 기록 {period.group(1)}까지로 실행한 결과입니다 "
                       f"(지금 데이터의 마지막 배당일은 {benji_last_div}). 다음 GPU 실행 때 최신 데이터로 갱신됩니다.")
        vals = [v for v in t["terms"].values()]
        a, b, c, d = st.columns(4)
        a.metric("모델", t["model"])
        b.metric(f"추출 {t['runs']}회 소요", f"{t['seconds']}초")
        c.metric("근거 검사 통과", t["verified_rate"])
        d.metric("평균 일치율", f"{sum(v['agreement'] for v in vals) / len(vals):.3f}")

        st.markdown("##### ① 투자설명서에서 뽑은 조건")
        rows = [{"항목": FIELD_KO.get(k, k), "값": v["value"] if v["value"] is not None else "(추출 안 됨)",
                 "근거 문장": ", ".join(f"S{i}" for i in v["evidence_ids"]) or "-", "일치율": v["agreement"],
                 "검사 결과": ", ".join(f"{s} {n}" for s, n in v["statuses"].items())} for k, v in t["terms"].items()]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        with st.expander("근거 문장 원문 보기"):
            for k, v in t["terms"].items():
                if v["value"] is not None:
                    st.markdown(f"**{FIELD_KO.get(k, k)}** — " + " ".join(f"`S{i}`" for i in v["evidence_ids"]))
                    for sent in v.get("evidence_sents", []):
                        st.markdown(f"> {md_safe(sent)}")

        st.markdown("##### ② 규칙 기반 자동 판정")
        badge = {"일치": "🟢", "검토 필요": "🟠", "확인 불가": "⚪"}
        for r in ai["table"]:
            with st.container(border=True):
                h1, h2 = st.columns([3, 1])
                h1.markdown(f"**{r['item']}**")
                h2.markdown(f"{badge.get(r['verdict'], '⚫')} **{r['verdict']}**")
                st.markdown(f"온체인: {r['chain']}  \n규칙: {r['rule']}")
                if r.get("doc_facts"):
                    ko = {"declaration_tied_to_nav": "배당은 NAV 계산일에 선언", "nav_only_on_open_days": "NAV는 개장일에만 계산",
                          "closed_on_weekends": "주말 휴장"}
                    st.caption("문서에서 찾은 사실: " + " · ".join(f"{ko[k]} {'✓' if v else '✗'}" for k, v in r["doc_facts"].items()))

        st.markdown("##### ③ AI 점검 리포트")
        rep = ai["report"]
        if "단정·당위 표현: ['" in rep.splitlines()[0]:
            st.warning("LLM 문장에 단정·당위 표현이 있어 하네스가 표시했습니다 (리포트 머리글 참고). 판정 자체는 규칙이 내린 것이라 바뀌지 않습니다.")
        body = []
        for line in rep.splitlines():
            if line.startswith("<!--") or line.startswith("# "):
                continue
            body.append("#### " + line[3:] if line.startswith("## ") else "##### " + line[4:] if line.startswith("### ") else line)
        with st.container(border=True):
            st.markdown(md_safe("\n".join(body)))
        st.download_button("리포트 내려받기 (Markdown)", rep.encode("utf-8"), "benji_report.md", "text/markdown")

        if ai["comp"]:
            st.markdown("##### ④ 모델 비교 (같은 하네스·같은 문서, 5회 반복)")
            st.dataframe(pd.DataFrame(ai["comp"]), width="stretch", hide_index=True)
            st.caption("RTX 5070 Ti (VRAM 16GB) 실측. 32B는 VRAM을 넘어 일부가 CPU에서 돌아 느립니다.")

# ---------------- 6. 이상 탐지 ----------------
with tabs[5]:
    fl = D["BUIDL"]["flows"]
    dv = fl[fl["class"] == "dividend"]
    mm = dv[dv["basis_mismatch"]]
    a, b, c = st.columns(3)
    a.metric("잔고로 설명 안 되는 배당", f"{len(mm):,}건", f"{len(mm) / len(dv) * 100:.1f}% of 배당 건수", delta_color="off")
    b.metric("금액", f"${mm['amount'].sum() / 1e6:,.2f}M", f"{mm['amount'].sum() / dv['amount'].sum() * 100:.1f}% of 배당액",
             delta_color="off")
    c.metric("해당 지갑", f"{mm['dst'].nunique()}개")
    st.markdown("기준: 배당 금액이 **'그 회차 지급률 × 직전 지급 이후 최고 잔고 × 3'** 을 넘으면 받은 지갑의 온체인 잔고로 설명되지 않는 배당으로 표시합니다.")
    top = (mm.groupby("dst")["amount"].agg(["size", "sum"]).sort_values("sum", ascending=False).head(10)
           .rename(columns={"size": "건수", "sum": "금액(달러)"}))
    top.index.name = "지갑"
    st.dataframe(top.style.format({"금액(달러)": "{:,.0f}"}), width="stretch")
    st.caption("BUIDL만 해당합니다 (BENJI 0건). 원인은 아직 미해결 — 다른 클래스나 장부 밖 보유분에 대한 배당일 가능성.")

# ---------------- 7. 원천 데이터 ----------------
with tabs[6]:
    f = st.radio("펀드", FUNDS, horizontal=True, key="raw_fund")
    fl = D[f]["flows"]
    classes = st.multiselect("구분", list(CLASS_KO.values()), default=["배당", "신규 청약", "상환"])
    rev = {v: k for k, v in CLASS_KO.items()}
    dmin, dmax = fl["date_et"].min().date(), fl["date_et"].max().date()
    rng = st.slider("기간 (미국 동부 기준)", min_value=dmin, max_value=dmax, value=(dmin, dmax))
    sel = fl[fl["class"].isin([rev[c] for c in classes])
             & (fl["date_et"].dt.date >= rng[0]) & (fl["date_et"].dt.date <= rng[1])].copy()
    sel["구분"] = sel["class"].map(CLASS_KO)
    view = sel[["ts_kst", "date_et", "구분", "fn", "src", "dst", "amount", "tx_hash"]]
    st.write(f"{len(view):,}건")
    st.dataframe(view, width="stretch", height=380)
    xbytes = excel_bytes(f, tuple(classes), rng[0], rng[1], SIG)
    d1, d2 = st.columns(2)
    d1.download_button("CSV 내려받기", view.to_csv(index=False).encode("utf-8-sig"), f"{f}_flows.csv", "text/csv")
    d2.download_button("Excel 내려받기 (거래 + 월별)", xbytes, f"{f}_flows.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------------- 8. AI 감사 관제실 ----------------
# 에이전트 관제실은 GPU PC에서 도는 별도 서버(agent/console_api.py, 포트 8700)라서 화면을 통째로 끼운다.
# 주소 후보: 환경변수 AUDIT_CONSOLE_URL → 외부 접속 스크립트가 적어 둔 dashboard/.console_url(터널 주소) → 이 PC.
# 화면은 보는 사람 브라우저가 직접 여므로, 다른 기기에서 볼 때는 터널 주소가 잡혀 있어야 한다.
def console_address():
    note = Path(__file__).with_name(".console_url")
    cands = [os.environ.get("AUDIT_CONSOLE_URL"), note.read_text(encoding="utf-8-sig").strip() if note.exists() else None,
             "http://localhost:8700"]
    for url in [c.rstrip("/") for c in cands if c]:
        try:
            with urllib.request.urlopen(url + "/agent/health", timeout=3) as r:
                if r.status == 200:
                    return url, True
        except Exception:
            pass
    return "http://localhost:8700", False


with tabs[7]:
    console_url, console_up = console_address()
    st.markdown("에이전트 여섯(총괄·문서 분석·조사·검증·감사·보고)과 담당자가 BENJI 배당 기록을 조사합니다. "
                "**조사 시작**을 누르면 에이전트가 움직이는 모습이 지도에 나타나고, 검증과 감사를 통과한 건은 "
                "보고서와 함께 결재란으로 올라옵니다. LLM은 이 PC의 GPU(Ollama)에서 돕니다.")
    if console_up:
        st.caption(f"관제실 화면: {console_url} · [새 창으로 크게 보기]({console_url})")
        st.iframe(console_url, height=960)
    else:
        st.info(f"관제실 서버({console_url})에 연결되지 않습니다. GPU PC에서 Langfuse(docker)와 관제실 서버를 켠 뒤 "
                "이 탭을 다시 여세요. 다른 기기나 클라우드 배포본에서는 GPU PC에서 외부 접속 스크립트(share.ps1)를 켜야 보입니다.")
