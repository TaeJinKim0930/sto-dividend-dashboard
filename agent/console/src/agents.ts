// 에이전트 정의. 이름은 LangGraph 노드 이름과 같아야 한다 (console_api.py).
export type AgentId = "총괄" | "문서 분석" | "조사" | "검증" | "감사" | "보고" | "결재";

export type AgentDef = {
  id: AgentId;
  role: string; // 카드에 보이는 한 줄
  detail: string; // 마우스를 올리면 보이는 설명
  tools: string[];
  llm: boolean; // LLM이 문장을 쓰는가
  human?: boolean;
};

export const AGENTS: AgentDef[] = [
  { id: "총괄", role: "조사 3건을 차례로 배정", detail: "조사 주제를 하나씩 꺼내 다음 에이전트에게 넘깁니다. 검증에서 기각되거나 결재가 끝나면 다음 주제로 넘어갑니다.", tools: [], llm: false },
  { id: "문서 분석", role: "투자설명서 원문 찾기", detail: "SEC에 낸 투자설명서(485BPOS)에서 주제와 관련된 문장을 찾고, 그 문장만 근거로 한 줄 요약합니다.", tools: ["prospectus_search"], llm: true },
  { id: "조사", role: "온체인 기록에서 숫자 확인", detail: "실제 BENJI 배당·환매·체인 이동 기록을 도구로 집계하고, 도구가 낸 숫자만 써서 두 문장으로 발견을 씁니다.", tools: ["weekend_profile", "detect_change_point", "upgrade_events", "redemption_events", "bridge_events"], llm: true },
  { id: "검증", role: "다른 방법으로 다시 계산", detail: "조사와 다른 계산 경로(원본 기록, 날짜에서 요일 재계산)로 숫자를 다시 냅니다. 통과·기각은 LLM이 아니라 코드가 판정합니다.", tools: ["recompute_weekend", "recompute_burn"], llm: true },
  { id: "감사", role: "주장 속 숫자의 근거 검사", detail: "조사 문장에 나온 숫자가 모두 도구 결과에 실제로 있는지 검사합니다. 하나라도 없으면 결재로 올리지 않고 총괄로 돌려보냅니다.", tools: ["check_citations"], llm: true },
  { id: "보고", role: "결재 보고서 작성", detail: "주장 속 숫자마다 도구 결과의 어느 칸에서 왔는지 코드로 찾고, 문장이 그 숫자를 원래 뜻대로 썼는지 LLM이 검사합니다. 재계산 대조표·투자설명서 근거·확인 사항을 묶어 승인/반려 권고와 함께 올립니다.", tools: ["map_numbers", "recompute_table"], llm: true },
  { id: "결재", role: "담당자가 승인·반려", detail: "검증과 감사를 통과한 건만 보고서와 함께 사람에게 옵니다. 결재란의 보고서 보기에서 내용을 확인하고 승인 또는 반려를 누르면 다음 건으로 넘어갑니다.", tools: [], llm: false, human: true },
];

export const CASES: { key: string; title: string }[] = [
  { key: "weekend", title: "BENJI 주말 배당은 왜 시작됐나" },
  { key: "redeem", title: "11월 4일 대규모 환매는 기록과 맞나" },
  { key: "bridge", title: "가설: 주말 배당은 다른 체인으로 옮긴 물량 때문" },
];
