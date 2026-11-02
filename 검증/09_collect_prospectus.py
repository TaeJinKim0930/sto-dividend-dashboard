# -*- coding: utf-8 -*-
"""BENJI(FOBXX) 투자설명서 수집 — SEC EDGAR 웹 스크래핑 (BeautifulSoup).

SEC는 자동 접근 시 User-Agent에 연락처 이메일을 요구한다 (.env SEC_USER_AGENT).
출력: data/docs/benji_485bpos_2026-08-01.htm (원본), .txt (본문 텍스트), dividend_sentences.txt (배당 문장)
"""
import os, re, time, urllib.request
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "data", "docs")
os.makedirs(OUT, exist_ok=True)
URL = "https://www.sec.gov/Archives/edgar/data/1786958/000165558926000970/c485bpos.htm"
BASE = "benji_485bpos_2026-08-01"


def env(k):
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f".env에 {k} 없음")


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": env("SEC_USER_AGENT"),
                                               "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    open(os.path.join(OUT, BASE + ".htm"), "wb").write(raw)

    soup = BeautifulSoup(raw, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    text = soup.get_text(" ")
    text = re.sub(r"\s+", " ", text).strip()
    open(os.path.join(OUT, BASE + ".txt"), "w", encoding="utf-8").write(text)

    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text)
    keys = ("dividend", "distribution", "net asset value", "nav", "business day", "weekend", "holiday", "reinvest")
    hits = [s for s in sents if any(k in s.lower() for k in keys)]
    with open(os.path.join(OUT, "dividend_sentences.txt"), "w", encoding="utf-8") as f:
        for s in hits:
            f.write(s.strip() + "\n\n")
    print(f"원본 {len(raw):,} bytes | 본문 {len(text):,}자 | 배당·NAV 관련 문장 {len(hits)}개")


if __name__ == "__main__":
    main()
