# 토큰화 펀드 배당 검증 자동화

서강대학교 AI·SW대학원 「생성형 AI와 파이썬 데이터분석」 기말 프로젝트 (A70021 김태진)

해외 토큰화 펀드 2개(BlackRock BUIDL, Franklin Templeton BENJI)의 **블록체인 배당 기록**을 수집·전처리·분석하고, 같은 펀드 **투자설명서의 배당 조건**을 로컬 LLM으로 추출해 서로 맞는지 점검합니다.

## 구성

| 폴더 | 내용 |
|---|---|
| `검증/` | 수집(`01`·`05`·`06`·`09`), 전처리(`07`), 분석·차트(`08`), 문서 대 온체인 대조(`10`) 스크립트와 결과 데이터 (`data/clean/`) |
| `llm/` | 생성형 AI 하네스(`harness.py`), 프롬프트, 출력 스키마, 실행 기록(`runs/`) |
| `dashboard/` | Streamlit 대시보드 (`app.py`) |
| `reports/` | LLM이 작성한 점검 리포트 |

## 실행

```bash
pip install -r requirements.txt
streamlit run dashboard/app.py          # 대시보드 (저장된 결과로 바로 실행)
```

데이터를 새로 수집하려면 `.env.example`을 `.env`로 복사해 값을 넣고 `검증/` 스크립트를 번호 순서대로 실행합니다. LLM 단계는 Ollama와 GPU가 필요합니다 (`llm/README.md`).

## 데이터 출처

- 블록체인 거래 기록: Blockscout API, Etherscan API (Ethereum)
- 투자설명서: SEC EDGAR (Franklin OnChain U.S. Government Money Fund, 485BPOS 2026-08-01)
