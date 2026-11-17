# -*- coding: utf-8 -*-
"""BUIDL(Ethereum) 토큰 이동 전체 수집 — Blockscout 공개 API (키 불필요).

출력: data/buidl_transfers.csv
  컬럼: timestamp, block, tx_hash, log_index, type, method, from, to, amount
  type: token_minting(발행) / token_burning(소각) / token_transfer(이전)
"""
import csv, json, os, time, urllib.error, urllib.parse, urllib.request

TOKEN = "0x7712c34205737192402172409a8f7ccef8aa2aec"   # BUIDL proxy
DECIMALS = 6
BASE = "https://eth.blockscout.com/api/v2"
UA = {"User-Agent": "Mozilla/5.0 (student-research-script)"}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "buidl_transfers.csv")


def get(url, tries=4, timeout=40):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if i == tries - 1:
                raise
            # 429(요청 과다): 서버가 알려 준 대기 시간 또는 30초·60초·90초 기다린 뒤 재시도 (2026-11-16, 일일 자동 실행 대비)
            ra = e.headers.get("Retry-After") if e.headers else None
            time.sleep(max(int(ra) if ra and ra.isdigit() else 0, 30 * (i + 1)) if e.code == 429 else 2 * (i + 1))
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


ZERO = "0x0000000000000000000000000000000000000000"


def collect(token, decimals):
    """Etherscan 호환 tokentx 조회로 한 번에 5천 건씩 받는다 (2026-11-02 변경).
    REST /transfers는 50건씩이라 2만 건에 15~27분 걸렸다. 두 방식의 결과(건수·금액·순서)가 같음을 확인했다.
    tokentx에는 거래 안 로그 순번이 없어서, log_index에는 API가 준 순서(블록·로그 순)를 전체 순번으로 넣는다.
    전처리(07)가 (block, log_index)로 정렬하므로 이 순서가 그대로 유지된다."""
    got, start = [], 0
    while True:
        q = urllib.parse.urlencode({"module": "account", "action": "tokentx", "contractaddress": token,
                                    "startblock": start, "endblock": 99999999, "page": 1, "offset": 5000, "sort": "asc"})
        res = get("https://eth.blockscout.com/api?" + q, timeout=180).get("result") or []
        got += res
        if len(res) < 5000:
            break
        start = int(res[-1]["blockNumber"])                     # 꽉 찼으면 마지막 블록부터 다시
        got = [x for x in got if int(x["blockNumber"]) < start]  # 겹치는 블록은 다음 요청 것으로
        time.sleep(0.5)
    return [{
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime(int(x["timeStamp"]))),
        "block": int(x["blockNumber"]),
        "tx_hash": x["hash"],
        "log_index": i,
        "type": "token_minting" if x["from"] == ZERO else "token_burning" if x["to"] == ZERO else "token_transfer",
        "method": x["input"][:10],
        "from": x["from"],
        "to": x["to"],
        "amount": int(x["value"]) / 10 ** decimals,
    } for i, x in enumerate(got)]


def main():
    rows = collect(TOKEN, DECIMALS)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"완료: {len(rows)}건 | 기간 {rows[0]['timestamp'][:10]} ~ {rows[-1]['timestamp'][:10]} -> {OUT}")


if __name__ == "__main__":
    main()
