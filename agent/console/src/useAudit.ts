// AG-UI 규약으로 LangGraph 스택 A와 이어지는 훅. 에이전트가 움직일 때마다 화면 상태가 바뀐다.
import { HttpAgent } from "@ag-ui/client";
import { useCallback, useRef, useState } from "react";
import type { AgentId } from "./agents";

export type AuditState = {
  case?: string | null;
  doc?: { note?: string; hits?: { sentence_no: number; text: string }[] };
  claim?: string;
  evidence?: Record<string, unknown>;
  verify?: { pass?: boolean; note?: string; recompute?: Record<string, unknown> };
  audit?: { pass?: boolean; numbers?: number; missing?: string[]; note?: string };
  report?: Report;
  results?: { case: string; title: string; claim: string; verify: string; audit: string; pass: boolean; decision: string | null; report?: Report }[];
};

export type Report = {
  case: string;
  title: string;
  recommendation: "승인 권고" | "반려 권고";
  reason: string;
  summary: string;
  claim: string;
  numbers: { number: string; source: string | null; tool_ko: string | null; meaning: string; value: unknown; claim_usage?: string | null; ok: boolean; why?: string | null }[];
  recompute: { item: string; investigation: unknown; recompute: unknown; match: boolean }[];
  doc: { note: string; query: string; hits: { sentence_no: number; text: string }[] };
  verify_note: string;
  audit_note: string;
  checklist: { item: string; detail: string; level: "decide" | "check" | "ok" }[];
};

export type Step = { agent: AgentId; case: string | null; start: number; end?: number };
export type Pending = { case: string; title: string; claim: string; report?: Report };
export type Phase = "idle" | "running" | "waiting" | "done" | "error";

export function useAudit() {
  const agentRef = useRef<HttpAgent | null>(null);
  const caseRef = useRef<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [active, setActive] = useState<AgentId | null>(null);
  const [state, setState] = useState<AuditState>({});
  const [steps, setSteps] = useState<Step[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [finishedAt, setFinishedAt] = useState<number | null>(null);
  const [runCount, setRunCount] = useState(0);

  const run = useCallback(async (forwardedProps?: Record<string, unknown>) => {
    const agent = agentRef.current;
    if (!agent) return;
    setPhase("running");
    let interrupted = false;
    try {
      await agent.runAgent(
        { forwardedProps },
        {
          onStepStartedEvent: ({ event }) => {
            const name = event.stepName as AgentId;
            setActive(name);
            setSteps((s) => [...s, { agent: name, case: caseRef.current, start: Date.now() }]);
          },
          onStepFinishedEvent: ({ event }) => {
            setSteps((s) => {
              const i = s.findLastIndex((x) => x.agent === event.stepName && !x.end);
              if (i < 0) return s;
              const c = [...s];
              c[i] = { ...c[i], end: Date.now() };
              return c;
            });
          },
          onStateSnapshotEvent: ({ event }) => {
            const snap = event.snapshot as AuditState;
            if (snap.case !== undefined && snap.case !== caseRef.current) {
              caseRef.current = snap.case ?? null;
              // 총괄 칸이 새 건을 배정한 것. 방금 끝난 총괄 단계도 새 건에 붙인다
              setSteps((s) => (s.length && s[s.length - 1].agent === "총괄" ? [...s.slice(0, -1), { ...s[s.length - 1], case: caseRef.current }] : s));
            }
            setState(snap);
          },
          onCustomEvent: ({ event }) => {
            if (event.name === "on_interrupt") {
              interrupted = true;
              const v = typeof event.value === "string" ? JSON.parse(event.value) : event.value;
              setPending(v as Pending);
            }
          },
          onRunErrorEvent: ({ event }) => {
            setError(event.message);
            setPhase("error");
          },
        },
      );
      if (interrupted) {
        setPhase("waiting");
        setActive("결재");
      } else {
        setPhase("done");
        setActive(null);
        setFinishedAt(Date.now());
        setRunCount((n) => n + 1);
      }
    } catch (e) {
      setError(String(e));
      setPhase("error");
    }
  }, []);

  const start = useCallback(() => {
    agentRef.current = new HttpAgent({ url: "/agent", threadId: `console-${Date.now()}`, initialState: {} });
    caseRef.current = null;
    setState({});
    setSteps([]);
    setPending(null);
    setError(null);
    setStartedAt(Date.now());
    setFinishedAt(null);
    void run();
  }, [run]);

  const decide = useCallback(
    (d: "승인" | "반려") => {
      setPending(null);
      void run({ command: { resume: d } });
    },
    [run],
  );

  return { phase, active, state, steps, pending, error, startedAt, finishedAt, runCount, start, decide };
}
