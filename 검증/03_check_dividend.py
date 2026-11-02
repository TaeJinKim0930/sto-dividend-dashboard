# -*- coding: utf-8 -*-
"""대량 발행이 '배당'인지 검증 — 지급액이 보유 잔고에 비례하는가.

배당이라면 같은 트랜잭션 안에서 (지급액 / 직전 잔고) 비율이 모든 수령자에게 거의 같아야 한다.
그 비율을 연율로 환산하면 미국 단기국채 금리(연 4~5% 수준)와 비슷해야 한다.

출력: data/dividend_check.txt, data/dividend_daily.png
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
ZERO = "0x0000000000000000000000000000000000000000"
out = open(os.path.join(D, "dividend_check.txt"), "w", encoding="utf-8")


def p(*a):
    out.write(" ".join(str(x) for x in a) + "\n")


df = pd.read_csv(os.path.join(D, "buidl_transfers.csv"))
df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
df["from"] = df["from"].str.lower()
df["to"] = df["to"].str.lower()
df = df.sort_values(["block", "log_index"]).reset_index(drop=True)
df = df.rename(columns={"from": "src", "to": "dst"})

# 트랜잭션별 발행 건수 -> 10건 이상이면 '일괄 발행 트랜잭션'
mint_cnt = df[df["type"] == "token_minting"].groupby("tx_hash").size()
batch_tx = set(mint_cnt[mint_cnt >= 10].index)

# 시간 순으로 잔고를 굴리면서, 일괄 발행 시점의 직전 잔고 대비 비율 계산
bal = {}
recs = []
for r in df.itertuples(index=False):
    a = r.amount
    if r.type == "token_minting" and r.tx_hash in batch_tx:
        before = bal.get(r.dst, 0.0)
        if before > 1:  # 잔고가 있는 지갑만 비율 계산
            recs.append((r.tx_hash, r.ts, r.method, r.dst, a, before, a / before))
    if r.src != ZERO:
        bal[r.src] = bal.get(r.src, 0.0) - a
    if r.dst != ZERO:
        bal[r.dst] = bal.get(r.dst, 0.0) + a

R = pd.DataFrame(recs, columns=["tx", "ts", "method", "to", "amount", "before", "ratio"])
per_tx = R.groupby("tx").agg(ts=("ts", "first"), method=("method", "first"),
                             n=("ratio", "size"), med=("ratio", "median"),
                             cv=("ratio", lambda s: s.std() / s.mean() if s.mean() else float("nan")),
                             total=("amount", "sum")).sort_values("ts")

p("=" * 70)
p("[1] 일괄 발행 트랜잭션 수:", len(per_tx), "| 비율 계산된 지급 건수:", len(R))
p("\n[2] 트랜잭션 안에서 비율의 변동계수(CV) — 0에 가까울수록 잔고에 정확히 비례")
p(per_tx["cv"].describe().to_string())
p("  CV < 0.01 인 트랜잭션 비율:", round((per_tx["cv"] < 0.01).mean() * 100, 1), "%")

per_tx["era"] = per_tx["ts"].apply(lambda t: "월배당기(~2025-01-22)" if t < pd.Timestamp("2025-01-23", tz="UTC") else "일배당기(2025-01-23~)")
per_tx["wd"] = per_tx["ts"].dt.day_name()

p("\n[3] 시기별 1회 지급 비율 중앙값과 연율 환산")
for era, g in per_tx.groupby("era"):
    med = g["med"].median()
    if "월배당" in era:
        ann = med * 12
        unit = "x12(월)"
    else:
        ann = med * 365 / (5 / 7) / 1  # 영업일 기준 근사 대신 아래 요일 보정 사용
        unit = "참고용"
    p(f"  {era}: 지급 {len(g)}회, 1회 비율 중앙값 {med:.6f}")
mon = per_tx[per_tx["era"].str.contains("월배당")]
day = per_tx[per_tx["era"].str.contains("일배당")]
p(f"  월배당기 연율 환산(중앙값 x 12): {mon['med'].median() * 12 * 100:.2f}%")
wk = day[day["wd"].isin(["Tuesday", "Wednesday", "Thursday", "Friday"])]["med"].median()
mo = day[day["wd"] == "Monday"]["med"].median()
p(f"  일배당기 화~금 1일 비율 중앙값: {wk:.7f} -> 연율 환산(x365): {wk * 365 * 100:.2f}%")
p(f"  일배당기 월요일 비율 중앙값: {mo:.7f} -> 화~금 대비 {mo / wk:.2f}배 (주말 3일분이면 약 3배)")

p("\n[4] 일배당기 요일별 지급 횟수와 비율 중앙값")
p(day.groupby("wd").agg(횟수=("med", "size"), 비율중앙값=("med", "median")).to_string())

p("\n[5] 일괄 발행 트랜잭션의 호출 함수")
p(per_tx["method"].value_counts().to_string())

p("\n[6] 비례하지 않는 일괄 발행 (CV >= 0.05) — 배당이 아닐 가능성")
odd = per_tx[per_tx["cv"] >= 0.05]
p(odd[["ts", "method", "n", "med", "cv", "total"]].to_string() if len(odd) else "  없음")

# 그래프: 일괄 발행 1회 비율을 연율로
fig, ax = plt.subplots(figsize=(11, 4))
x = per_tx["ts"]
y = per_tx.apply(lambda r: r["med"] * (12 if "월배당" in r["era"] else 365) * 100, axis=1)
ax.scatter(x, y, s=8, color="#8B1A1A")
ax.axvline(pd.Timestamp("2025-01-23", tz="UTC"), color="#888", ls="--", lw=1)
ax.set_title("BUIDL 배당 1회 지급 비율의 연율 환산 (월배당기 x12, 일배당기 x365)")
ax.set_ylabel("연율 환산 %")
ax.set_ylim(0, 20)
fig.tight_layout()
fig.savefig(os.path.join(D, "dividend_daily.png"), dpi=110)
out.close()
print("OK")
