<!-- 생성: 2026-11-16 21:13 | harness v2.2 | dry_run=True | 모델: mock | 입력에 없는 숫자: 없음 | 단정·당위 표현: 없음 | 작성 2회 (피드백 재시도: 1회차 숫자 ['27.3', '9,999,999'], 표현 ['상충', '선언되어야 하']) -->
# BENJI 배당 점검 리포트

> 판정은 파이썬 규칙이 내렸다. 요약과 '검토가 필요한 이유'만 로컬 LLM(mock)이 썼다.
> LLM 문장 검사 — 입력에 없는 숫자: 없음 / 단정·당위 표현: 없음 / 작성 2회 (피드백 재시도: 1회차 숫자 ['27.3', '9,999,999'], 표현 ['상충', '선언되어야 하'])

## 요약

BENJI의 배당 선언일 항목이 검토 필요로 판정됐다. 업그레이드(2025-05-23) 뒤 주말 지급이 관측됐다.

## 검토가 필요한 항목

### 배당 선언일 (주말·휴일 포함 여부)

- **문서 원문:** "The Fund intends to declare income dividends from its net investment income each day when it makes its final net asset value (NAV) calculation. / The Fund is open for business and calculates its NAV every day on which both the New York Stock Exchange (NYSE) and the Federal Reserve Bank of New York (FRBNY) are open for business. / Both the NYSE and FRBNY are also closed on weekends and may be closed because of an emergency or other unanticipated event."
- **온체인 관측:** 업그레이드(2025-05-23) 전 주말 지급 0.0% (125회) -> 후 27.5% (527회)
- **판정 규칙:** 문서: 배당은 NAV 계산일에 선언 + NAV는 NYSE·FRBNY가 여는 날에만 계산 + 주말 휴장 → 주말 선언 없음이 기대됨. 온체인 주말 지급 > 0 → 검토 필요
- **검토가 필요한 이유:** 문서는 NAV를 계산하는 날마다 배당을 선언한다고 적고 있고, 주말은 휴장일이다. 온체인에서는 업그레이드 뒤 주말 지급이 관측되어 사람의 확인이 필요하다.

## 문서와 일치하는 항목

- **배당 지급 형태:** 문서 "Your income dividends and capital gain distributions will be automatically reinvested in additional shares at NAV on the payable date, which has the effect of compounding of dividends." / 온체인 배당 653회 모두 신규 토큰 발행(mint)

## 온체인으로 확인할 수 없는 항목

- 없음

## 판정 보류·추출 실패

- **보수:** 문서에서 추출 실패
- **목표 주가:** 문서에서 추출 실패

## 데이터의 한계

- 블록체인: Ethereum만. 다른 체인에 발행된 물량과 장부 밖 보유분은 포함하지 않는다
- 배당 기록 기간: 2024-11-20 ~ 2026-11-15 (배당 653회)
- 문서: SEC EDGAR 485BPOS, 2026-08-01
- '검토 필요'는 위반 판단이 아니라 사람이 확인할 지점이라는 뜻이다
