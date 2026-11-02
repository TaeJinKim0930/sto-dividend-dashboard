# -*- coding: utf-8 -*-
"""BUIDL(Ethereum) 토큰 이동 전체 수집 — Blockscout 공개 API (키 불필요).

출력: data/buidl_transfers.csv
  컬럼: timestamp, block, tx_hash, log_index, type, method, from, to, amount
  type: token_minting(발행) / token_burning(소각) / token_transfer(이전)
"""
import csv, json, os, time, urllib.parse, urllib.request

TOKEN = "0x7712c34205737192402172409a8f7ccef8aa2aec"   # BUIDL proxy
DECIMALS = 6
BASE = "https://eth.blockscout.com/api/v2"
UA = {"User-Agent": "Mozilla/5.0 (student-research-script)"}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "buidl_transfers.csv")


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def main():
    rows, params, page = [], None, 0
    while True:
        url = f"{BASE}/tokens/{TOKEN}/transfers"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        d = get(url)
        for it in d.get("items", []):
            total = it.get("total") or {}
            amt = int(total.get("value") or 0) / 10 ** DECIMALS
            rows.append({
                "timestamp": it.get("timestamp"),
                "block": it.get("block_number"),
                "tx_hash": it.get("transaction_hash"),
                "log_index": it.get("log_index"),
                "type": it.get("type"),
                "method": it.get("method"),
                "from": (it.get("from") or {}).get("hash"),
                "to": (it.get("to") or {}).get("hash"),
                "amount": amt,
            })
        page += 1
        params = d.get("next_page_params")
        if page % 10 == 0:
            print(f"  {page} pages, {len(rows)} rows ...")
        if not params:
            break
        time.sleep(0.35)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"완료: {len(rows)}건, {page}페이지 -> {OUT}")


if __name__ == "__main__":
    main()
