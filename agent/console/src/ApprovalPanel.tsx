// 결재란. 조사·검증·감사 칸에는 에이전트가, 담당자 칸에는 사람이 도장을 찍는다.
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CASES, type AgentId } from "./agents";
import { ReportDialog } from "./ReportDialog";
import type { AuditState, Pending, Phase, Step } from "./useAudit";

type Seal = { text: string; tone: "ok" | "no" } | null;

function SealCell({ who, seal }: { who: string; seal: Seal }) {
  return (
    <div className="flex flex-col border-r last:border-r-0">
      <div className="border-b py-1 text-center text-[11px] text-muted-foreground">{who}</div>
      <div className="grid h-[68px] place-items-center">
        {seal && (
          <span
            key={seal.text}
            className={cn(
              "stamp-in grid size-12 place-items-center rounded-full border-2 text-[13px] font-bold",
              seal.tone === "ok" ? "border-seal text-seal" : "border-muted-foreground text-muted-foreground",
            )}
          >
            {seal.text}
          </span>
        )}
      </div>
    </div>
  );
}

export function ApprovalPanel({ phase, state, steps, pending, decide, start }: { phase: Phase; state: AuditState; steps: Step[]; pending: Pending | null; decide: (d: "승인" | "반려") => void; start: () => void }) {
  const cur = pending?.case ?? state.case ?? state.results?.at(-1)?.case ?? null;
  const done = (id: AgentId) => steps.some((s) => s.case === cur && s.agent === id && s.end);
  const result = state.results?.find((r) => r.case === cur);
  const isCurrent = state.case === cur || (state.case == null && cur === state.results?.at(-1)?.case);
  const v = isCurrent ? state.verify : undefined;
  const a = isCurrent ? state.audit : undefined;
  const rep = pending?.report ?? (state.report?.case === cur ? state.report : undefined);
  const seals: Seal[] = [
    done("조사") ? { text: "조사", tone: "ok" } : null,
    done("검증") && v ? (v.pass ? { text: "확인", tone: "ok" } : { text: "기각", tone: "no" }) : null,
    done("감사") && a ? (a.pass ? { text: "확인", tone: "ok" } : { text: "반송", tone: "no" }) : null,
    done("보고") && rep && rep.case === cur ? (rep.recommendation === "승인 권고" ? { text: "확인", tone: "ok" } : { text: "주의", tone: "no" }) : null,
    result?.decision === "승인" ? { text: "승인", tone: "ok" } : result?.decision === "반려" ? { text: "반려", tone: "no" } : null,
  ];
  const title = CASES.find((c) => c.key === cur)?.title;

  return (
    <div className="flex h-full flex-col">
      <div>
        <h2 className="text-[15px] font-semibold">
          결재란 <span className="font-normal text-muted-foreground">(출처: LangGraph interrupt · AG-UI)</span>
        </h2>
        <p className="text-xs text-muted-foreground">{title ?? "조사 전"}</p>
      </div>
      <div className="mt-2 grid grid-cols-5 rounded-md border">
        <SealCell who="조사" seal={seals[0]} />
        <SealCell who="검증" seal={seals[1]} />
        <SealCell who="감사" seal={seals[2]} />
        <SealCell who="보고" seal={seals[3]} />
        <SealCell who="담당자" seal={seals[4]} />
      </div>

      {pending ? (
        <div className="mt-4 flex flex-1 flex-col">
          <p className="text-xs font-medium text-wait">결재 요청이 왔습니다</p>
          {rep && (
            <p className={cn("mt-1 text-sm font-semibold", rep.recommendation === "반려 권고" ? "text-fail" : "text-pass")}>
              보고 에이전트: {rep.recommendation}
              <span className="ml-1 font-normal text-muted-foreground">· {rep.reason}</span>
            </p>
          )}
          <p className="mt-2 line-clamp-4 text-sm leading-relaxed">{rep?.summary || pending.claim}</p>
          <div className="mt-auto space-y-2 pt-4">
            {rep && <ReportDialog report={rep} steps={steps} decide={decide} canDecide={!!pending} />}
            <div className="flex gap-2">
              <Button className="flex-1" onClick={() => decide("승인")}>승인</Button>
              <Button className="flex-1" variant="outline" onClick={() => decide("반려")}>반려</Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-4 flex flex-1 flex-col text-sm text-muted-foreground">
          {phase === "idle" && <p>조사를 시작하면 세 건이 차례로 흐르고, 검증과 감사를 통과한 건만 이 자리로 결재가 올라옵니다.</p>}
          {phase === "running" && <p>에이전트가 일하는 중입니다. 결재할 건이 생기면 여기에 뜹니다.</p>}
          {phase === "done" && <p>세 건을 모두 처리했습니다. 아래 기록에서 에이전트별 입력과 출력을 볼 수 있습니다.</p>}
          {phase === "error" && <p className="text-fail">실행이 멈췄습니다. 백엔드(8700)와 Ollama가 켜져 있는지 확인한 뒤 다시 시작하세요.</p>}
          {(phase === "idle" || phase === "done" || phase === "error") && (
            <Button className="mt-auto" onClick={start}>{phase === "idle" ? "조사 시작" : "다시 조사"}</Button>
          )}
        </div>
      )}
    </div>
  );
}
