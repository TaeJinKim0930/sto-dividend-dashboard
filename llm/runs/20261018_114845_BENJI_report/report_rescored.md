<!-- 생성: 2026-10-18 12:02 | harness v2.1 | 재채점(원응답 20261018_114845_BENJI_report) | 모델: qwen2.5:32b | 입력에 없는 숫자: 없음 | 단정·당위 표현: 없음 -->
# BENJI 배당 점검 리포트

> 판정은 파이썬 규칙이 내렸다. 요약과 '검토가 필요한 이유'만 로컬 LLM(qwen2.5:32b)이 썼다.
> LLM 문장 검사 — 입력에 없는 숫자: 없음 / 단정·당위 표현: 없음

## 요약

배당 선언일에 주말·휴일이 포함되는지에 대한 검토가 필요합니다. 배당 지급 형태는 일치합니다. 보수와 목표 주가는 확인이 불가능합니다.

## 검토가 필요한 항목

### 배당 선언일 (주말·휴일 포함 여부)

- **문서 원문:** "The Fund intends to declare income dividends from its net investment income each day when it makes its final net asset value (NAV) calculation. Distributions The Fund intends to declare income dividends from its net investment income each day when it makes its final net asset value calculation and reinvests them daily. / The Fund is open for business and calculates its NAV every day on which both the New York Stock Exchange (NYSE) and the Federal Reserve Bank of New York (FRBNY) are open for business. / Both the NYSE and FRBNY are also closed on weekends and may be closed because of an emergency or other unanticipated event."
- **온체인 관측:** 업그레이드(2025-05-23) 전 주말 지급 0.0% (125회) -> 후 27.4% (489회)
- **판정 규칙:** 문서: 배당은 NAV 계산일에 선언 + NAV는 NYSE·FRBNY가 여는 날에만 계산 + 주말 휴장 → 주말 선언 없음이 기대됨. 온체인 주말 지급 > 0 → 검토 필요
- **검토가 필요한 이유:** 업그레이드 후 주말 배당 지급 비율이 27.4%로 증가하여, 문서에 명시된 배당 선언일과 실제 지급일 사이의 차이가 관측되었습니다. 이는 검토가 필요합니다.

## 문서와 일치하는 항목

- **배당 지급 형태:** 문서 "Your income dividends and capital gain distributions will be automatically reinvested in additional shares at NAV on the payable date, which has the effect of compounding of dividends. Your income dividends and capital gain distributions will be automatically reinvested in additional shares at net asset value on the payable date, which has the effect of compounding of dividends." / 온체인 배당 615회 모두 신규 토큰 발행(mint)

## 온체인으로 확인할 수 없는 항목

- **보수:** 문서 "Annual Fund Operating Expenses (expenses that you pay each year as a percentage of the value of your investment) Management fees 0.15 % Distribution and service (12b-1) fees None Other expenses 0.07 % Total annual Fund operating expenses 0.22 % Fee waiver and/or expense reimbursement 1 - 0.02 % Total annual Fund operating expenses after fee waiver and/or expense reimbursement 0.20 % 1." — 온체인 데이터로 확인할 수 없는 항목
- **목표 주가:** 문서 "The Fund also tries to maintain a stable $1.00 share price." — 온체인 데이터로 확인할 수 없는 항목

## 데이터의 한계

- 블록체인: Ethereum만. 다른 체인에 발행된 물량과 장부 밖 보유분은 포함하지 않는다
- 배당 기록 기간: 2024-11-20 ~ 2026-10-06 (배당 615회)
- 문서: SEC EDGAR 485BPOS, 2026-08-01
- '검토 필요'는 위반 판단이 아니라 사람이 확인할 지점이라는 뜻이다
