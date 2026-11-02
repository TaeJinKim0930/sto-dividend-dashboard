# -*- coding: utf-8 -*-
"""BUIDL 수집 데이터 탐색 — 배당 패턴 확인과 전처리 이슈 도출.

입력: data/buidl_transfers.csv
출력: data/analysis.txt, data/buidl_mint_days.png
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
out = open(os.path.join(D, "analysis.txt"), "w", encoding="utf-8")


def p(*a):
    out.write(" ".join(str(x) for x in a) + "\n")


df = pd.read_csv(os.path.join(D, "buidl_transfers.csv"))
df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
df["day"] = df["ts"].dt.date
df["from"] = df["from"].str.lower()
df["to"] = df["to"].str.lower()

p("=" * 70)
p("[1] 전체 규모")
p("  행 수:", len(df), "| 고유 트랜잭션:", df["tx_hash"].nunique())
p("  기간:", df["ts"].min(), "~", df["ts"].max())
p("  중복 (tx_hash, log_index):", df.duplicated(["tx_hash", "log_index"]).sum())
p("  결측:", dict(df[["timestamp", "from", "to", "amount", "method"]].isna().sum()))

p("\n[2] 유형별")
g = df.groupby("type").agg(건수=("amount", "size"), 합계=("amount", "sum"))
p(g.to_string())

mint = df[df["type"] == "token_minting"].copy()
burn = df[df["type"] == "token_burning"].copy()

p("\n[3] 발행(mint) 호출 함수 분포 — 배당과 신규 청약 구분 단서")
p(mint["method"].value_counts(dropna=False).to_string())

p("\n[4] 발행일별 집계 (수령 지갑 수 기준 상위 15일)")
days = mint.groupby("day").agg(발행건수=("amount", "size"),
                               수령지갑=("to", "nunique"),
                               발행량=("amount", "sum"),
                               트랜잭션=("tx_hash", "nunique"))
p(days.sort_values("수령지갑", ascending=False).head(15).to_string())

p("\n[5] 하루 수령 지갑 수 분포 (배당일 판별 기준을 정하기 위함)")
p(days["수령지갑"].describe().to_string())
p("  수령지갑 >= 10 인 날:", (days["수령지갑"] >= 10).sum(), "일")
p("  수령지갑 >= 20 인 날:", (days["수령지갑"] >= 20).sum(), "일")

batch = days[days["수령지갑"] >= 10].copy()
batch.index = pd.to_datetime(batch.index)
p("\n[6] 대량 발행일(수령 지갑 10개 이상)의 일자 분포 — 월초에 몰리면 월 배당")
p(batch.index.day.value_counts().sort_index().to_string())
p("\n  대량 발행일 목록:")
p(batch.sort_index().to_string())

p("\n[7] 월별 대량 발행 합계 (배당 후보)")
m = batch["발행량"].resample("MS").sum()
p(m[m > 0].to_string())

p("\n[8] 소각(burn) = 상환 후보")
p("  건수:", len(burn), "| 합계:", round(burn["amount"].sum(), 2))
p(burn["method"].value_counts(dropna=False).to_string())

# 현재 잔고 재구성 (이동 기록으로)
inflow = df[df["to"] != ZERO].groupby("to")["amount"].sum()
outflow = df[df["from"] != ZERO].groupby("from")["amount"].sum()
bal = inflow.sub(outflow, fill_value=0)
bal = bal[bal > 1e-6].sort_values(ascending=False)
p("\n[9] 이동 기록으로 재구성한 현재 잔고")
p("  보유 지갑 수:", len(bal), "| 합계:", round(bal.sum(), 2))
top = bal.head(5)
p("  상위 5개 비중:", round(top.sum() / bal.sum() * 100, 1), "%")
p("  상위 1개 비중:", round(bal.iloc[0] / bal.sum() * 100, 1), "%")
p(top.to_string())

# 그래프: 일별 발행 수령 지갑 수
fig, ax = plt.subplots(figsize=(11, 4))
dd = days.copy()
dd.index = pd.to_datetime(dd.index)
ax.bar(dd.index, dd["수령지갑"], width=2, color="#8B1A1A")
ax.axhline(10, color="#888", ls="--", lw=1)
ax.set_title("BUIDL(Ethereum) 일별 발행 수령 지갑 수 — 튀는 날 = 배당 후보")
ax.set_ylabel("수령 지갑 수")
fig.tight_layout()
fig.savefig(os.path.join(D, "buidl_mint_days.png"), dpi=110)

out.close()
print("OK")
