# -*- coding: utf-8 -*-
"""BENJI(Ethereum) 이동 기록 + 프록시 업그레이드 이력 수집.

이동 기록: Blockscout (키 불필요) -> data/benji_transfers.csv
업그레이드: ERC1967 Upgraded(address) 이벤트, Etherscan V2 getLogs (.env 키) -> data/benji_upgrades.csv
"""
import csv, json, os, time, urllib.parse, urllib.request
from eth_utils import keccak

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
D = os.path.join(HERE, "data")
TOKEN = "0x3ddc84940ab509c11b20b76b466933f40b750dc9"
DECIMALS = 18
UA = {"User-Agent": "Mozilla/5.0 (student-research-script)"}


def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if i == 3:
                raise
            time.sleep(2 * (i + 1))


def key():
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        if line.startswith("ETHERSCAN_API_KEY="):
            return line.split("=", 1)[1].strip()


def transfers():
    rows, params = [], None
    while True:
        url = f"https://eth.blockscout.com/api/v2/tokens/{TOKEN}/transfers"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        d = get(url)
        for it in d.get("items", []):
            rows.append({
                "timestamp": it.get("timestamp"), "block": it.get("block_number"),
                "tx_hash": it.get("transaction_hash"), "log_index": it.get("log_index"),
                "type": it.get("type"), "method": it.get("method"),
                "from": (it.get("from") or {}).get("hash"), "to": (it.get("to") or {}).get("hash"),
                "amount": int((it.get("total") or {}).get("value") or 0) / 10 ** DECIMALS,
            })
        params = d.get("next_page_params")
        if not params:
            break
        time.sleep(0.35)
    with open(os.path.join(D, "benji_transfers.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    return rows


def upgrades():
    t0 = "0x" + keccak(text="Upgraded(address)").hex()
    q = urllib.parse.urlencode({"chainid": 1, "module": "logs", "action": "getLogs", "address": TOKEN,
                                "topic0": t0, "fromBlock": 0, "toBlock": "latest",
                                "page": 1, "offset": 1000, "apikey": key()})
    d = get("https://api.etherscan.io/v2/api?" + q)
    res = d.get("result") if d.get("status") == "1" else []
    rows = [{"ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(lg["timeStamp"], 16))),
             "block": int(lg["blockNumber"], 16), "tx_hash": lg["transactionHash"],
             "implementation": "0x" + lg["topics"][1][-40:]} for lg in (res or [])]
    with open(os.path.join(D, "benji_upgrades.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ts_utc", "block", "tx_hash", "implementation"])
        w.writeheader(); w.writerows(rows)
    return rows


if __name__ == "__main__":
    tr = transfers()
    print(f"BENJI 이동 기록 {len(tr)}건 | 기간 {min(r['timestamp'] for r in tr)} ~ {max(r['timestamp'] for r in tr)}")
    ups = upgrades()
    print(f"업그레이드(Upgraded 이벤트) {len(ups)}건")
    for u in ups:
        print(f"  {u['ts_utc']} -> {u['implementation']}")
