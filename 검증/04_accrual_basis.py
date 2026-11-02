# -*- coding: utf-8 -*-
"""배당 지급 기준 확인: 비율이 어긋나는 수령자는 최근 잔고 변동이 있던 지갑인가?

각 일괄 발행 트랜잭션에서 수령자의 비율이 그 트랜잭션 중앙값의 +-5% 안이면 '정상 비례'.
정상 비례 여부를 '직전 7일 내 자기 잔고 변동(입출금) 유무'와 교차한다.
출력: data/accrual_basis.txt
"""
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
ZERO = "0x0000000000000000000000000000000000000000"
df = pd.read_csv(os.path.join(D, "buidl_transfers.csv"))
df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.rename(columns={"from": "src", "to": "dst"})
df["src"] = df["src"].str.lower(); df["dst"] = df["dst"].str.lower()
df = df.sort_values(["block", "log_index"]).reset_index(drop=True)

mint_cnt = df[df["type"] == "token_minting"].groupby("tx_hash").size()
batch_tx = set(mint_cnt[mint_cnt >= 10].index)
is_div = df["tx_hash"].isin(batch_tx) & (df["type"] == "token_minting")

# 배당이 아닌 잔고 변동 이벤트(청약 발행, 상환 소각, 이전)를 지갑별 시각 목록으로
flows = df[~is_div]
touch = {}
for r in flows.itertuples(index=False):
    for w in (r.src, r.dst):
        if w != ZERO:
            touch.setdefault(w, []).append(r.ts)

bal, recs = {}, []
for r in df.itertuples(index=False):
    a = r.amount
    if r.tx_hash in batch_tx and r.type == "token_minting":
        before = bal.get(r.dst, 0.0)
        if before > 1:
            recent = any(pd.Timedelta(0) < (r.ts - t) <= pd.Timedelta(days=7) for t in touch.get(r.dst, []))
            recs.append((r.tx_hash, r.ts, r.dst, a / before, recent))
    if r.src != ZERO: bal[r.src] = bal.get(r.src, 0.0) - a
    if r.dst != ZERO: bal[r.dst] = bal.get(r.dst, 0.0) + a

R = pd.DataFrame(recs, columns=["tx", "ts", "wallet", "ratio", "recent_flow"])
R["med"] = R.groupby("tx")["ratio"].transform("median")
R["ok"] = (R["ratio"] / R["med"] - 1).abs() <= 0.05
R["era"] = R["ts"].apply(lambda t: "월배당기" if t < pd.Timestamp("2025-01-23", tz="UTC") else "일배당기")

o = open(os.path.join(D, "accrual_basis.txt"), "w", encoding="utf-8")
o.write("전체 지급 건수: %d\n" % len(R))
o.write("트랜잭션 중앙값 +-5%% 안(정상 비례) 비율: %.1f%%\n\n" % (R["ok"].mean() * 100))
o.write("[시기별 정상 비례 비율]\n")
o.write(R.groupby("era")["ok"].mean().mul(100).round(1).to_string() + "\n\n")
o.write("[직전 7일 내 잔고 변동 유무 x 정상 비례]  (값 = 정상 비례 비율 %, 괄호 = 건수)\n")
for era, g in R.groupby("era"):
    for flag, h in g.groupby("recent_flow"):
        o.write("  %s | 최근 변동 %s : %.1f%%  (%d건)\n" % (era, "있음" if flag else "없음", h["ok"].mean() * 100, len(h)))
o.write("\n[어긋나는 수령자가 반복되는가 — 어긋남 비율 상위 지갑]\n")
w = R.groupby("wallet").agg(지급=("ok", "size"), 어긋남비율=("ok", lambda s: round((1 - s.mean()) * 100, 1)))
o.write(w.sort_values("어긋남비율", ascending=False).head(10).to_string() + "\n")
o.close()
print("OK")
