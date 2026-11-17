import { Moon, Play, Sun } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { AgentMap } from "./AgentMap";
import { ApprovalPanel } from "./ApprovalPanel";
import { CaseLedger } from "./CaseLedger";
import { AgentTimeChart, GpuChart, useMetrics } from "./Metrics";
import { TracePanel } from "./TracePanel";
import { useAudit } from "./useAudit";

function Panel({ title, source, note, className, children }: { title?: string; source?: string; note?: string; className?: string; children: ReactNode }) {
  return (
    <section className={cn("rounded-lg border bg-card p-4", className)}>
      {title && (
        <div className="mb-2">
          <h2 className="text-[15px] font-semibold">
            {title}
            {source && <span className="ml-1 font-normal text-muted-foreground">(출처: {source})</span>}
          </h2>
          {note && <p className="text-xs text-muted-foreground">{note}</p>}
        </div>
      )}
      {children}
    </section>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: string; tone?: string }) {
  return (
    <div className="min-w-0 px-5 py-3 first:pl-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn("mt-0.5 truncate text-xl font-semibold tabular-nums", tone)}>{value}</p>
      {sub && <p className="truncate text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

export default function App() {
  const audit = useAudit();
  const { series, now } = useMetrics();
  const [dark, setDark] = useState(() => localStorage.getItem("theme") === "dark");
  const [traceKey, setTraceKey] = useState(0);
  const [, tick] = useState(0);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);
  // 결재로 멈추거나 실행이 끝날 때마다 추적 기록을 다시 읽는다
  useEffect(() => {
    if (audit.phase === "waiting" || audit.phase === "done") setTraceKey((k) => k + 1);
  }, [audit.phase]);
  // 조사 중에는 경과 시간을 1초마다 다시 그린다
  useEffect(() => {
    if (audit.phase !== "running" && audit.phase !== "waiting") return;
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [audit.phase]);

  const { phase, active, state, steps, pending } = audit;
  const results = state.results ?? [];
  const passed = results.filter((r) => r.pass).length;
  const elapsed = audit.startedAt ? ((audit.finishedAt ?? Date.now()) - audit.startedAt) / 1000 : null;
  const busy = phase === "running" || phase === "waiting";
  const g = now?.gpu ?? {};

  return (
    <TooltipProvider>
      <div className="mx-auto max-w-[1480px] px-6 pb-10 pt-5">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-[26px] font-bold tracking-tight">감사 관제실</h1>
            <p className="text-sm text-muted-foreground">
              토큰화 펀드 BENJI의 실제 배당 기록을 에이전트 여섯과 담당자 한 명이 조사합니다. 흐름은 LangGraph, 화면 연결은 AG-UI, 기록은 Langfuse, 화면 틀은 shadcn/ui.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="mr-2 text-xs text-muted-foreground">모델 {now?.model ?? "–"} · 이 PC의 GPU</span>
            <Button variant="outline" size="icon" aria-label={dark ? "밝은 화면으로" : "어두운 화면으로"} onClick={() => setDark((d) => !d)}>
              {dark ? <Sun /> : <Moon />}
            </Button>
            <Button onClick={audit.start} disabled={busy}>
              <Play />
              {phase === "idle" ? "조사 시작" : busy ? "조사 중" : "다시 조사"}
            </Button>
          </div>
        </header>

        <p className="mt-4 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">지금 상황</span> (출처: AG-UI 이벤트 · nvidia-smi · Ollama)
        </p>
        <div className="mt-1.5 grid grid-cols-2 divide-x rounded-lg border bg-card md:grid-cols-5">
          <Stat
            label="지금 일하는 에이전트"
            value={phase === "running" ? active ?? "–" : phase === "waiting" ? "담당자" : phase === "done" ? "모두 끝남" : "대기"}
            sub={state.case ? `조사 대상 ${state.case}` : undefined}
            tone={phase === "running" ? "text-run" : phase === "waiting" ? "text-wait" : undefined}
          />
          <Stat label="결재 대기" value={pending ? "1건" : "0건"} sub={pending ? pending.title : "통과한 건만 사람에게"} tone={pending ? "text-wait" : undefined} />
          <Stat label="검증·근거 검사 통과" value={`${passed} / ${results.length}`} sub="감사까지 간 건 중 둘 다 통과" />
          <Stat
            label="GPU"
            value={g.util !== undefined ? `${g.util.toFixed(0)}%` : "–"}
            sub={g.mem_used ? `VRAM ${(g.mem_used / 1024).toFixed(1)} / ${((g.mem_total ?? 0) / 1024).toFixed(0)}GB · ${g.temp}°C` : undefined}
          />
          <Stat label="이번 조사 시간" value={elapsed !== null ? `${elapsed.toFixed(0)}초` : "–"} sub="결재 기다린 시간 포함" />
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-12">
          <Panel title="에이전트 지도" source="React Flow · LangGraph · AG-UI" note="칸에 마우스를 올리면 하는 일과 쓰는 도구가 보입니다" className="lg:col-span-8">
            <div className="h-[360px]">
              <AgentMap phase={phase} active={active} state={state} steps={steps} pending={pending} />
            </div>
          </Panel>
          <Panel className="lg:col-span-4">
            <ApprovalPanel phase={phase} state={state} steps={steps} pending={pending} decide={audit.decide} start={audit.start} />
          </Panel>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-12">
          <Panel title="조사 장부" source="LangGraph 상태 · AG-UI" note="세 건이 차례로 흐릅니다" className="lg:col-span-6">
            <CaseLedger phase={phase} active={active} state={state} steps={steps} />
          </Panel>
          <Panel title="에이전트별 시간" source="Recharts · AG-UI" note="이번 조사, 결재 기다린 시간 제외" className="lg:col-span-3">
            <AgentTimeChart steps={steps} />
          </Panel>
          <Panel title="GPU 사용률" source="Recharts · nvidia-smi" note="최근 3분" className="lg:col-span-3">
            <GpuChart series={series} />
            <p className="text-[11px] text-muted-foreground">LLM이 문장을 쓸 때마다 솟습니다. 올라온 모델: {now?.models.join(", ") || "없음"}</p>
          </Panel>
        </div>

        {audit.error && <p className="mt-4 rounded-md border border-fail/40 bg-fail/5 p-3 text-sm text-fail">{audit.error}</p>}

        <Panel className="mt-4 h-[620px]">
          <TracePanel refreshKey={traceKey} />
        </Panel>
      </div>
    </TooltipProvider>
  );
}
