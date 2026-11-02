# -*- coding: utf-8 -*-
"""BUIDL 규제·운영 이벤트 수집 — Etherscan V2 getLogs (무료 키, .env).

대상: 이전/승인/발행을 뺀 모든 이벤트 (소각·강제이전 사유, 정지, 화이트리스트, 옴니버스, 프록시 업그레이드)
ABI: 구현체 DSToken ABI(data/buidl_impl_abi.json) + 프록시 ABI(Blockscout에서 조회)
출력: data/buidl_events.csv  (event, block, ts_utc, tx_hash, log_index, args_json)
"""
import csv, json, os, time, urllib.parse, urllib.request
from eth_abi import decode
from eth_utils import keccak, to_checksum_address

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
D = os.path.join(HERE, "data")
PROXY = "0x7712c34205737192402172409a8f7ccef8aa2aec"
UA = {"User-Agent": "Mozilla/5.0 (student-research-script)"}
SKIP = {"Transfer", "Approval", "Issue"}   # 이미 이전 기록으로 확보


def load_key():
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        if line.startswith("ETHERSCAN_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(".env에 ETHERSCAN_API_KEY 없음")


def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if i == 3:
                raise
            time.sleep(2 * (i + 1))


def sig(ev):
    return f"{ev['name']}({','.join(i['type'] for i in ev['inputs'])})"


def main():
    key = load_key()
    impl_abi = json.load(open(os.path.join(D, "buidl_impl_abi.json"), encoding="utf-8"))
    proxy_abi = get(f"https://eth.blockscout.com/api/v2/smart-contracts/{PROXY}").get("abi", [])
    events = {}
    for ev in impl_abi + proxy_abi:
        if ev.get("type") == "event" and ev["name"] not in SKIP:
            events["0x" + keccak(text=sig(ev)).hex()] = ev

    rows, summary = [], {}
    for t0, ev in events.items():
        page, n = 1, 0
        while True:
            q = urllib.parse.urlencode({
                "chainid": 1, "module": "logs", "action": "getLogs", "address": PROXY,
                "topic0": t0, "fromBlock": 0, "toBlock": "latest",
                "page": page, "offset": 1000, "apikey": key})
            d = get("https://api.etherscan.io/v2/api?" + q)
            res = d.get("result")
            if d.get("status") != "1" or not isinstance(res, list):
                if str(d.get("message", "")).startswith("No records"):
                    break
                raise SystemExit(f"Etherscan 오류 [{ev['name']}]: {d.get('message')} / {res}")
            for lg in res:
                idx = [i for i in ev["inputs"] if i.get("indexed")]
                non = [i for i in ev["inputs"] if not i.get("indexed")]
                args = {}
                for i, tp in zip(idx, lg["topics"][1:]):
                    v = decode([i["type"]], bytes.fromhex(tp[2:]))[0]
                    args[i["name"]] = v
                if non:
                    vals = decode([i["type"] for i in non], bytes.fromhex(lg["data"][2:]))
                    args.update({i["name"]: v for i, v in zip(non, vals)})
                for k, v in list(args.items()):
                    if isinstance(v, bytes):
                        args[k] = "0x" + v.hex()
                    elif isinstance(v, str) and v.startswith("0x") and len(v) == 42:
                        args[k] = v.lower()
                ts = int(lg["timeStamp"], 16)
                rows.append({
                    "event": ev["name"],
                    "block": int(lg["blockNumber"], 16),
                    "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
                    "tx_hash": lg["transactionHash"],
                    "log_index": int(lg["logIndex"], 16) if lg.get("logIndex") not in (None, "0x") else 0,
                    "args_json": json.dumps(args, default=str, ensure_ascii=False),
                })
                n += 1
            if len(res) < 1000:
                break
            page += 1
            time.sleep(0.25)
        summary[ev["name"]] = n
        time.sleep(0.25)

    rows.sort(key=lambda r: (r["block"], r["log_index"]))
    out = os.path.join(D, "buidl_events.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["event", "block", "ts_utc", "tx_hash", "log_index", "args_json"])
        w.writeheader()
        w.writerows(rows)
    print("이벤트별 건수:")
    for k, v in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print(f"합계 {len(rows)}건 -> {out}")


if __name__ == "__main__":
    main()
