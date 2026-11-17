// 조사 세 건의 진행 장부.
import { cn } from "@/lib/utils";
import { AGENTS, CASES } from "./agents";
import type { AuditState, Phase, Step } from "./useAudit";

export function CaseLedger({ phase, active, state, steps }: { phase: Phase; active: string | null; state: AuditState; steps: Step[] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-xs text-muted-foreground">
          <th className="py-2 pr-3 font-normal">조사 주제</th>
          <th className="py-2 pr-3 font-normal">거쳐 간 에이전트</th>
          <th className="py-2 pr-3 font-normal">결과</th>
          <th className="py-2 text-right font-normal">걸린 시간</th>
        </tr>
      </thead>
      <tbody>
        {CASES.map((c) => {
          const mine = steps.filter((s) => s.case === c.key && s.end);
          const r = state.results?.find((x) => x.case === c.key);
          const isCur = state.case === c.key;
          const sec = mine.filter((s) => s.agent !== "결재").reduce((t, s) => t + (s.end! - s.start), 0) / 1000;
          let tag = "대기";
          let tone = "text-muted-foreground";
          if (r?.decision === "승인") [tag, tone] = ["승인", "text-pass"];
          else if (r?.decision === "반려") [tag, tone] = ["반려", "text-fail"];
          else if (r?.decision === "검증에서 기각") [tag, tone] = ["검증에서 기각", "text-fail"];
          else if (isCur && phase === "waiting") [tag, tone] = ["결재 대기", "text-wait"];
          else if (isCur && phase === "running") [tag, tone] = [`${active ?? ""} 진행 중`, "text-run"];
          return (
            <tr key={c.key} className={cn("border-b last:border-b-0", isCur && phase !== "done" && "bg-run/5")}>
              <td className="py-2.5 pr-3">{c.title}</td>
              <td className="py-2.5 pr-3">
                <div className="flex gap-1">
                  {AGENTS.map((a) => {
                    const hit = mine.some((s) => s.agent === a.id);
                    return (
                      <span
                        key={a.id}
                        title={a.id}
                        className={cn("h-1.5 w-6 rounded-full", hit ? (a.human ? "bg-wait" : "bg-run") : "bg-muted")}
                      />
                    );
                  })}
                </div>
              </td>
              <td className={cn("py-2.5 pr-3 font-medium", tone)}>{tag}</td>
              <td className="py-2.5 text-right tabular-nums text-muted-foreground">{mine.length ? `${sec.toFixed(1)}초` : "–"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
