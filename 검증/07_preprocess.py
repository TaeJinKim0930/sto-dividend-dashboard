# -*- coding: utf-8 -*-
"""전처리 — 확정 방안(검증/전처리_방안.md) 구현. BUIDL·BENJI 공통.

입력 (data/): buidl_transfers.csv, buidl_events.csv, benji_transfers.csv, selectors.json
출력 (data/clean/):
  {fund}_flows.csv     행 단위 분류 (dividend / subscription / redemption / swap_in / swap_out / bridge_in / bridge_out / transfer)
  {fund}_dividends.csv 배당 트랜잭션 단위 (경과일 정규화 지급률, 시기 구분)
  {fund}_wallets.csv   지갑 단위 (배당 비례 이탈률, 특수 지갑 표시)
  {fund}_monthly.csv   월 단위 재합산 (#2)
  checks.txt           정합성 검사
"""
import json, os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
OUT = os.path.join(D, "clean")
os.makedirs(OUT, exist_ok=True)
ZERO = "0x0000000000000000000000000000000000000000"
DUST = 1e-6   # 토큰 0.000001개 이하 잔고는 부동소수점 잔여(먼지)로 보고 0 처리
SEL = json.load(open(os.path.join(D, "selectors.json"), encoding="utf-8"))
SUBSCRIBE_FN = {"bulkRegisterAndIssuance", "issueTokens", "issueTokensCustom"}
log = []


def fn_name(m):
    """#5 호출 함수 해석: 셀렉터 -> 함수 이름"""
    if isinstance(m, str) and m.startswith("0x") and SEL.get(m):
        return SEL[m][0].split("(")[0]
    return m


def load(fund):
    df = pd.read_csv(os.path.join(D, f"{fund}_transfers.csv"))
    df = df.rename(columns={"from": "src", "to": "dst"})
    df["src"] = df["src"].str.lower()
    df["dst"] = df["dst"].str.lower()
    # #7 시간: UTC 원본 유지 + 미국 동부(분석 기준) + 한국(표시용)
    df["ts_utc"] = pd.to_datetime(df["timestamp"], utc=True)
    df["ts_et"] = df["ts_utc"].dt.tz_convert("America/New_York")
    df["ts_kst"] = df["ts_utc"].dt.tz_convert("Asia/Seoul")
    df["date_et"] = df["ts_et"].dt.date
    df["fn"] = df["method"].apply(fn_name)
    return df.sort_values(["block", "log_index"]).reset_index(drop=True)


def balances_pass(df):
    """시간 순으로 잔고를 굴려, 각 행 직전의 수령자 잔고와 보유자 수를 붙인다."""
    bal, before, holders = {}, [], []
    for r in df.itertuples(index=False):
        before.append(bal.get(r.dst, 0.0))
        holders.append(sum(1 for v in bal.values() if v > DUST))
        if r.src != ZERO:
            bal[r.src] = bal.get(r.src, 0.0) - r.amount
        if r.dst != ZERO:
            bal[r.dst] = bal.get(r.dst, 0.0) + r.amount
    df["bal_before"] = before
    df["holders_before"] = holders
    return df, bal


def classify(fund, df, events):
    mint = df["type"] == "token_minting"
    m = df[mint].copy()
    m["ratio"] = m["amount"] / m["bal_before"].where(m["bal_before"] > DUST)
    g = m.groupby("tx_hash").agg(n=("dst", "nunique"), holders=("holders_before", "first"),
                                 with_bal=("bal_before", lambda s: (s > DUST).mean()),
                                 med=("ratio", "median"))
    # #1 배당 판별(경제적 정의): 이미 잔고가 있는 지갑 2개 이상에게, 잔고의 1% 미만씩, 같은 트랜잭션에서 동시 발행
    #    ('보유자 절반 이상' 조건은 배당을 받지 않는 보유 지갑이 많아 불안정 -> 제거)
    g["is_div"] = (g["n"] >= 2) & (g["with_bal"] >= 0.9) & (g["med"] < 0.01)
    div_tx = set(g[g["is_div"]].index)

    reason = {}
    if events is not None:
        b = events[events["event"] == "Burn"]
        for r in b.itertuples(index=False):
            a = json.loads(r.args_json)
            reason[(r.tx_hash.lower(), round(int(a["value"]) / 1e6, 6))] = a.get("reason") or ""

    # 행 단위 판별: 배당은 '트랜잭션 지급률 x 직전 지급 이후 최고 잔고'를 넘을 수 없다.
    #   - 일할 계산이라 지급 직전 잔고만 보면, 막 상환한 지갑의 정상 배당이 청약으로 오분류된다 (BUIDL)
    #   - 한 트랜잭션에 배당과 청약이 묶이는 경우가 있다 (BENJI 서명 실행)
    proper = m[m["tx_hash"].isin(div_tx) & (m["bal_before"] > DUST) & (m["ratio"] < 0.01)]
    tx_rate = proper.groupby("tx_hash")["ratio"].median().to_dict()
    bal, peak, row_peak = {}, {}, {}
    for idx, r in zip(df.index, df.itertuples(index=False)):
        if r.type == "token_minting" and r.tx_hash in div_tx:
            row_peak[idx] = max(peak.get(r.dst, 0.0), r.bal_before)
        if r.src != ZERO:
            bal[r.src] = bal.get(r.src, 0.0) - r.amount
            peak[r.src] = max(peak.get(r.src, 0.0), bal[r.src])
        if r.dst != ZERO:
            bal[r.dst] = bal.get(r.dst, 0.0) + r.amount
            if r.type == "token_minting" and r.tx_hash in div_tx:
                peak[r.dst] = bal[r.dst]          # 배당을 받았으면 다음 기간을 새로 시작
            else:
                peak[r.dst] = max(peak.get(r.dst, 0.0), bal[r.dst])

    def over_cap(idx, r):
        """배당 상한(지급률 x 기간 최고 잔고 x 여유 3배)을 넘는가"""
        pk = row_peak.get(idx, 0.0)
        return pk <= DUST or r.amount > tx_rate.get(r.tx_hash, 0.0) * pk * 3

    def is_div_row(idx, r):
        if r.tx_hash not in div_tx:
            return False
        if fund == "buidl":
            # BUIDL: 배당 전용 함수(bulkIssuance)의 동시 지급은 전부 배당.
            #        상한 초과 행은 '잔고 기준 불일치'로 표시만 한다 (온체인 잔고로 설명 안 되는 배당)
            return r.fn == "bulkIssuance"
        # BENJI 등: 함수로 구분 불가 -> 상한을 넘는 행은 같은 트랜잭션에 묶인 청약
        return not over_cap(idx, r)

    def cls(idx, r):
        if r.type == "token_minting":
            if r.fn == "swapDSToken":
                return "swap_in"
            if r.fn == "deliver":
                return "bridge_in"
            return "dividend" if is_div_row(idx, r) else "subscription"
        if r.type == "token_burning":
            # #4 소각 분리: 사유 로그 우선, 없으면 호출 함수
            rs = reason.get((r.tx_hash.lower(), round(r.amount, 6)))
            if rs == "bridge" or r.fn == "bridgeDSTokens":
                return "bridge_out"
            if rs == "dstoken-swap" or r.fn == "swapDSToken":
                return "swap_out"
            return "redemption"
        return "transfer"

    df["class"] = [cls(i, r) for i, r in zip(df.index, df.itertuples(index=False))]
    df["basis_mismatch"] = [
        (c == "dividend") and over_cap(i, r)
        for i, r, c in zip(df.index, df.itertuples(index=False), df["class"])]
    dv = df[df["class"] == "dividend"]
    log.append(f"[{fund}] 배당 행 중 잔고 기준 불일치: {int(dv['basis_mismatch'].sum())}건 "
               f"({dv['basis_mismatch'].mean() * 100:.1f}%), 금액 {dv.loc[dv['basis_mismatch'], 'amount'].sum():,.0f} "
               f"/ 배당 총액 {dv['amount'].sum():,.0f}, 해당 지갑 {dv.loc[dv['basis_mismatch'], 'dst'].nunique()}개")

    # 판별 규칙 검증 (BUIDL: 함수 이름과 대조)
    if fund == "buidl":
        d = df[df["class"] == "dividend"]
        log.append(f"[{fund}] 배당 판별 행 중 bulkIssuance 비율: {(d['fn'] == 'bulkIssuance').mean() * 100:.1f}%")
        s = df[(df["class"] == "subscription")]
        log.append(f"[{fund}] 청약 판별 행 중 청약용 함수 비율: {s['fn'].isin(SUBSCRIBE_FN).mean() * 100:.1f}% "
                   f"(그 외 함수: {s.loc[~s['fn'].isin(SUBSCRIBE_FN), 'fn'].value_counts().to_dict()})")
    return df, m


def dividends_table(df):
    d = df[df["class"] == "dividend"].copy()
    d["ratio"] = d["amount"] / d["bal_before"].where(d["bal_before"] > DUST)
    t = d.groupby("tx_hash").agg(ts_et=("ts_et", "first"), date_et=("date_et", "first"),
                                 recipients=("dst", "nunique"), total=("amount", "sum"),
                                 med_ratio=("ratio", "median")).sort_values("ts_et")
    # #3 경과일 정규화: 직전 지급일과의 실제 일수로 나눠 1일 지급률
    t["gap_days"] = pd.to_datetime(t["date_et"]).diff().dt.days
    t.loc[t["gap_days"] == 0, "gap_days"] = float("nan")   # 같은 날 두 번째 지급: 경과일 0 -> 정규화 제외
    t["daily_rate"] = t["med_ratio"] / t["gap_days"]
    t["annual_pct"] = t["daily_rate"] * 365 * 100
    t["weekday_et"] = pd.to_datetime(t["date_et"]).dt.day_name()
    # #2 시기 구분: 지급 간격 20일 이상이면 월배당기
    t["era"] = t["gap_days"].apply(lambda x: "monthly" if pd.notna(x) and x >= 20 else "daily")
    return t.reset_index()


def wallets_table(df, final_bal):
    d = df[df["class"] == "dividend"].copy()
    d["ratio"] = d["amount"] / d["bal_before"].where(d["bal_before"] > DUST)
    d["tx_med"] = d.groupby("tx_hash")["ratio"].transform("median")
    d["dev"] = (d["ratio"] / d["tx_med"] - 1).abs() > 0.05
    w = d.groupby("dst").agg(dividends=("dev", "size"), dev_rate=("dev", "mean"),
                             ratio_vs_med=("ratio", lambda s: (s / d.loc[s.index, "tx_med"]).median()))
    w["balance_now"] = [final_bal.get(a, 0.0) for a in w.index]
    # #6 특수 지갑: 비례 이탈률 90% 이상 & 지급 10회 이상 -> 별도 그룹
    w["special"] = (w["dev_rate"] >= 0.9) & (w["dividends"] >= 10)
    return w.reset_index().rename(columns={"dst": "wallet"})


def monthly_table(df):
    x = df.copy()
    x["month"] = x["ts_et"].dt.tz_localize(None).dt.to_period("M").astype(str)
    p = x.pivot_table(index="month", columns="class", values="amount", aggfunc="sum", fill_value=0)
    inflow = p.reindex(columns=["dividend", "subscription", "swap_in", "bridge_in"], fill_value=0).sum(axis=1)
    outflow = p.reindex(columns=["redemption", "swap_out", "bridge_out"], fill_value=0).sum(axis=1)
    p["net_supply_change"] = inflow - outflow
    p["supply_end"] = p["net_supply_change"].cumsum()
    return p.reset_index()


def run(fund, events=None):
    df = load(fund)
    df, final_bal = balances_pass(df)
    df, _ = classify(fund, df, events)
    div = dividends_table(df)
    wal = wallets_table(df, final_bal)
    mon = monthly_table(df)

    cols = ["ts_utc", "ts_et", "ts_kst", "date_et", "block", "tx_hash", "log_index",
            "type", "fn", "class", "basis_mismatch", "src", "dst", "amount", "bal_before"]
    df[cols].to_csv(os.path.join(OUT, f"{fund}_flows.csv"), index=False, encoding="utf-8")
    div.to_csv(os.path.join(OUT, f"{fund}_dividends.csv"), index=False, encoding="utf-8")
    wal.to_csv(os.path.join(OUT, f"{fund}_wallets.csv"), index=False, encoding="utf-8")
    mon.to_csv(os.path.join(OUT, f"{fund}_monthly.csv"), index=False, encoding="utf-8")

    # 정합성 검사
    minted = df.loc[df["type"] == "token_minting", "amount"].sum()
    burned = df.loc[df["type"] == "token_burning", "amount"].sum()
    cs = df.groupby("class")["amount"].agg(["size", "sum"])
    ins = cs.reindex(["dividend", "subscription", "swap_in", "bridge_in"])["sum"].fillna(0).sum()
    outs = cs.reindex(["redemption", "swap_out", "bridge_out"])["sum"].fillna(0).sum()
    log.append(f"\n[{fund}] 분류 결과\n" + cs.to_string())
    log.append(f"[{fund}] 발행 합계 대사: 분류 합 {ins:,.6f} vs 원본 {minted:,.6f} -> 차이 {ins - minted:,.6f}")
    log.append(f"[{fund}] 소각 합계 대사: 분류 합 {outs:,.6f} vs 원본 {burned:,.6f} -> 차이 {outs - burned:,.6f}")
    log.append(f"[{fund}] 재구성 공급량 {mon['supply_end'].iloc[-1]:,.6f} / 잔고 합 {sum(v for v in final_bal.values() if v > DUST):,.6f}")
    log.append(f"[{fund}] 배당 트랜잭션 {len(div)}건 | 특수 지갑 {int(wal['special'].sum())}개 / 배당 수령 지갑 {len(wal)}개")
    return df, div, wal, mon


if __name__ == "__main__":
    ev = pd.read_csv(os.path.join(D, "buidl_events.csv"))
    run("buidl", ev)
    run("benji", None)
    open(os.path.join(OUT, "checks.txt"), "w", encoding="utf-8").write("\n".join(log) + "\n")
    print("\n".join(log))
