# -*- coding: utf-8 -*-
"""정제 데이터 분석 — 인사이트와 차트 (3차 STEP 04 재료).

입력: data/clean/{buidl,benji}_*.csv, data/benji_upgrades.csv
출력: data/clean/insights.txt, data/clean/fig_*.png
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
HERE = os.path.dirname(os.path.abspath(__file__))
C = os.path.join(HERE, "data", "clean")
RED, GRAY, BLUE = "#8B1A1A", "#9A9A9A", "#2F5D8A"
out = open(os.path.join(C, "insights.txt"), "w", encoding="utf-8")


def p(*a):
    out.write(" ".join(str(x) for x in a) + "\n")


def load(fund):
    dv = pd.read_csv(os.path.join(C, f"{fund}_dividends.csv"), parse_dates=["date_et"])
    fl = pd.read_csv(os.path.join(C, f"{fund}_flows.csv"))
    mo = pd.read_csv(os.path.join(C, f"{fund}_monthly.csv"))
    wa = pd.read_csv(os.path.join(C, f"{fund}_wallets.csv"))
    return dv, fl, mo, wa


bd, bf, bm, bw = load("buidl")
jd, jf, jm, jw = load("benji")

# ---------- 1. 정규화 지급률 (#3 효과 검증) ----------
p("=" * 70)
p("[1] 경과일 정규화 전후 — 지급 1회 비율의 흩어짐")
for name, d in (("BUIDL", bd), ("BENJI", jd)):
    x = d.dropna(subset=["daily_rate"])
    raw = x["med_ratio"] * 365 * 100
    norm = x["annual_pct"]
    p(f"  {name}: 정규화 전 연율 표준편차 {raw.std():.2f}%p -> 정규화 후 {norm.std():.2f}%p "
      f"(중앙값 {norm.median():.2f}%)")

fig, ax = plt.subplots(figsize=(11, 4.2))
x = bd.dropna(subset=["daily_rate"])
ax.scatter(x["date_et"], x["med_ratio"] * 365 * 100, s=7, color=GRAY, alpha=0.6, label="BUIDL 정규화 전 (1회 비율 x365)")
ax.plot(x["date_et"], x["annual_pct"], color=RED, lw=1.6, label="BUIDL 경과일 정규화 후")
y = jd.dropna(subset=["daily_rate"])
ax.plot(y["date_et"], y["annual_pct"], color=BLUE, lw=1.2, label="BENJI 경과일 정규화 후")
ax.axvline(pd.Timestamp("2025-01-23"), color="#555", ls="--", lw=1)
ax.text(pd.Timestamp("2025-01-28"), 17.5, "BUIDL 월배당 → 매일 배당", fontsize=9, color="#555")
ax.set_ylim(0, 20)
ax.set_ylabel("연율 환산 지급률 (%)")
ax.set_title("배당 지급률 — 경과일로 나누면 요일·공휴일 띠가 한 줄로 모인다")
ax.legend(loc="upper right", fontsize=8.5, frameon=False)
fig.tight_layout(); fig.savefig(os.path.join(C, "fig_rate_normalized.png"), dpi=120); plt.close(fig)

# ---------- 2. 지급 요일 (문서 대 실제) ----------
p("\n[2] 배당 지급 요일 (미국 동부 기준)")
order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
kor = ["월", "화", "수", "목", "금", "토", "일"]
wk = pd.DataFrame({
    "BUIDL(매일 배당기)": bd[bd["era"] == "daily"]["weekday_et"].value_counts().reindex(order, fill_value=0),
    "BENJI": jd["weekday_et"].value_counts().reindex(order, fill_value=0)})
wk.index = kor
p(wk.to_string())
wkend = jd["weekday_et"].isin(["Saturday", "Sunday"])
p(f"  BENJI 주말 배당: {int(wkend.sum())}회 / 전체 {len(jd)}회 ({wkend.mean() * 100:.1f}%)")
p("  투자설명서(2026-08-01): 'declare income dividends ... each day when it makes its final NAV calculation'")
p("  -> NAV 계산은 영업일. 온체인은 주말에도 배당 발행 => 문서 대 실제 대조 후보 (원문 재확인 필요)")

fig, ax = plt.subplots(figsize=(7, 3.6))
wk.plot(kind="bar", ax=ax, color=[RED, BLUE], width=0.75)
ax.set_title("배당 지급 요일 — BUIDL은 평일, BENJI는 주말 포함 매일")
ax.set_ylabel("지급 횟수"); ax.set_xlabel(""); ax.tick_params(axis="x", rotation=0)
ax.legend(frameon=False, fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(C, "fig_weekday.png"), dpi=120); plt.close(fig)

# BENJI 주말 배당이 업그레이드 시점과 관련 있는가
up = pd.read_csv(os.path.join(HERE, "data", "benji_upgrades.csv"), parse_dates=["ts_utc"])
p("\n[3] BENJI 업그레이드 전후 주말 배당 비율")
cuts = [pd.Timestamp("2000-01-01")] + [t.tz_localize(None) for t in up["ts_utc"]
                                       if t > pd.Timestamp("2024-11-01", tz="UTC")] + [pd.Timestamp("2100-01-01")]
for a, b in zip(cuts[:-1], cuts[1:]):
    seg = jd[(jd["date_et"] >= a) & (jd["date_et"] < b)]
    if len(seg):
        p(f"  {seg['date_et'].min().date()} ~ {seg['date_et'].max().date()}: 지급 {len(seg)}회, "
          f"주말 비율 {seg['weekday_et'].isin(['Saturday', 'Sunday']).mean() * 100:.1f}%")

# ---------- 4. 자금 흐름 (#4 소각 분리 효과) ----------
p("\n[4] BUIDL 자금 흐름 합계 (달러)")
fl = bf.groupby("class")["amount"].sum()
for k in ["subscription", "dividend", "swap_in", "bridge_in", "redemption", "swap_out", "bridge_out"]:
    p(f"  {k:12s} {fl.get(k, 0):>18,.0f}")
p(f"  소각 중 실제 상환 비율: {fl['redemption'] / (fl['redemption'] + fl['swap_out'] + fl['bridge_out']) * 100:.1f}%")

m = bm.copy()
m["month"] = pd.to_datetime(m["month"])
fig, ax = plt.subplots(figsize=(11, 4.2))
col = lambda k: m[k] / 1e6 if k in m else pd.Series(0.0, index=m.index)
sub, swi, bri = col("subscription"), col("swap_in"), col("bridge_in")
red, swo, bro = col("redemption"), col("swap_out"), col("bridge_out")
# 유입(+): 청약 / 클래스 전환 유입 / 체인 유입 — 유출(-): 상환 / 클래스 전환 / 체인 이동
ax.bar(m["month"], sub, width=20, color=BLUE, label="신규 청약")
ax.bar(m["month"], swi, bottom=sub, width=20, color="#E8C35A", label="클래스 전환 유입")
ax.bar(m["month"], bri, bottom=sub + swi, width=20, color="#C9C9C9", label="체인 유입")
ax.bar(m["month"], -red, width=20, color=RED, label="상환")
ax.bar(m["month"], -swo, bottom=-red, width=20, color="#D4A017", label="클래스 전환 유출")
ax.bar(m["month"], -bro, bottom=-(red + swo), width=20, color=GRAY, label="체인 이동")
ax2 = ax.twinx()
ax2.plot(m["month"], m["supply_end"] / 1e6, color="black", lw=1.5, label="월말 잔고")
ax.axhline(0, color="black", lw=0.6)
ax.set_ylim(-(red + swo + bro).max() * 1.08, (sub + swi + bri).max() * 1.08)   # 누적 막대가 잘리지 않게
ax.set_ylabel("월간 유입(+) / 유출(-), 백만 달러"); ax2.set_ylabel("월말 잔고, 백만 달러")
ax.set_title("BUIDL(Ethereum) 월별 자금 흐름 — 소각을 사유별로 나눈 결과")
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, loc="lower left", fontsize=8.5, frameon=False, ncol=3)
fig.tight_layout(); fig.savefig(os.path.join(C, "fig_flows.png"), dpi=120); plt.close(fig)

# ---------- 5. 잔고 기준 불일치 배당 ----------
p("\n[5] BUIDL 잔고 기준 불일치 배당")
dv = bf[bf["class"] == "dividend"]
mm = dv[dv["basis_mismatch"]]
p(f"  불일치 {len(mm)}건 / 배당 {len(dv)}건 ({len(mm) / len(dv) * 100:.1f}%)")
p(f"  금액 {mm['amount'].sum():,.0f} / {dv['amount'].sum():,.0f} 달러 ({mm['amount'].sum() / dv['amount'].sum() * 100:.1f}%)")
top = mm.groupby("dst")["amount"].agg(["size", "sum"]).sort_values("sum", ascending=False).head(5)
p("  불일치 금액 상위 지갑:\n" + top.to_string())

# ---------- 6. 업그레이드 비교 ----------
p("\n[6] 업그레이드 이력 비교")
p("  BUIDL: 프록시 ProxyTargetSet 1회(2024-03-01 배포 시점) -> 운영 중 업그레이드 0회. 서비스 컨트랙트 12개도 배포일 이후 변경 없음")
p(f"  BENJI: ERC1967 Upgraded {len(up)}회 — " + ", ".join(t.strftime('%Y-%m-%d') for t in up['ts_utc']))
p("         2024-08-22 3회는 배포 직후 10분 내 초기 설정, 운영 중 업그레이드는 2025-05-23, 2026-02-12 두 번")

# ---------- 7. 보유 집중도 ----------
p("\n[7] 현재 보유 집중도")
for name, w, fl_ in (("BUIDL", bw, bf), ("BENJI", jw, jf)):
    ZERO = "0x0000000000000000000000000000000000000000"
    inflow = fl_[fl_["dst"] != ZERO].groupby("dst")["amount"].sum()
    outflow = fl_[fl_["src"] != ZERO].groupby("src")["amount"].sum()
    bal = inflow.sub(outflow, fill_value=0)
    bal = bal[bal > 1e-6].sort_values(ascending=False)
    p(f"  {name}: 보유 지갑 {len(bal)}개, 상위 1개 {bal.iloc[0] / bal.sum() * 100:.1f}%, "
      f"상위 5개 {bal.head(5).sum() / bal.sum() * 100:.1f}%")
out.close()
print("OK")
