// 에이전트 지도: React Flow(@xyflow/react). 지금 일하는 칸이 파랗게 뛰고, 방금 넘어온 연결선이 움직인다.
import { Background, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { Bot, Check, FileText, Hand, Scale, ShieldCheck, UserRound, Wrench, X } from "lucide-react";
import { useMemo } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { AGENTS, CASES, type AgentDef, type AgentId } from "./agents";
import type { AuditState, Pending, Phase, Step } from "./useAudit";

type Status = "idle" | "running" | "waiting" | "done" | "rejected" | "skipped";
type AgentNodeData = { def: AgentDef; status: Status; line?: string; sec?: number };

const ICON: Record<AgentId, typeof Bot> = { 총괄: Scale, "문서 분석": Bot, 조사: Bot, 검증: ShieldCheck, 감사: ShieldCheck, 보고: FileText, 결재: UserRound };
const STATUS_TEXT: Record<Status, string> = { idle: "대기", running: "일하는 중", waiting: "결재 대기", done: "끝남", rejected: "기각", skipped: "건너뜀" };

function AgentNode({ data }: NodeProps<Node<AgentNodeData>>) {
  const { def, status, line, sec } = data;
  const Icon = ICON[def.id];
  const h = "!h-1.5 !w-1.5 !min-w-0 !border-0 !bg-border";
  return (
    <Tooltip delayDuration={150}>
      <TooltipTrigger asChild>
        <div
          className={cn(
            "w-[200px] rounded-lg border bg-card px-3.5 py-3 text-left transition-colors",
            status === "running" && "beacon border-run",
            status === "waiting" && "border-wait bg-wait/5",
            status === "done" && "border-pass/50",
            status === "rejected" && "border-fail/60",
            (status === "idle" || status === "skipped") && "opacity-70",
          )}
        >
          <Handle type="target" position={Position.Left} id="l-t" className={h} />
          <Handle type="source" position={Position.Left} id="l-s" className={h} />
          <Handle type="target" position={Position.Right} id="r-t" className={h} />
          <Handle type="source" position={Position.Right} id="r-s" className={h} />
          <Handle type="source" position={Position.Top} id="top-s" className={h} />
          <Handle type="target" position={Position.Top} id="top-t" className={h} />
          <Handle type="source" position={Position.Bottom} id="bot-s" className={h} />
          <Handle type="target" position={Position.Bottom} id="bot-t" className={h} />
          <div className="flex items-center gap-2">
            <Icon className="size-4 text-muted-foreground" aria-hidden />
            <span className="text-[15px] font-semibold">{def.id}</span>
            {def.human && <span className="rounded bg-wait/15 px-1.5 text-[11px] font-medium text-wait">사람</span>}
            <span
              className={cn(
                "ml-auto flex items-center gap-1 text-[11px]",
                status === "running" && "text-run",
                status === "waiting" && "text-wait",
                status === "done" && "text-pass",
                status === "rejected" && "text-fail",
                (status === "idle" || status === "skipped") && "text-muted-foreground",
              )}
            >
              {status === "done" && <Check className="size-3" />}
              {status === "rejected" && <X className="size-3" />}
              {status === "waiting" && <Hand className="size-3" />}
              {status === "running" && <span className="size-1.5 rounded-full bg-run" />}
              {STATUS_TEXT[status]}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">{def.role}</p>
          <p className={cn("mt-2 line-clamp-2 min-h-[2.5em] text-xs leading-snug", line ? "text-foreground" : "text-muted-foreground/60")}>
            {line ?? (def.llm ? "LLM이 문장을 씁니다" : def.human ? "통과한 건만 옵니다" : "코드가 흐름을 정합니다")}
          </p>
          {sec !== undefined && <p className="mt-1 text-[11px] text-muted-foreground">{sec.toFixed(1)}초</p>}
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-[280px] p-3 text-xs leading-relaxed">
        <p className="font-semibold">{def.id}</p>
        <p className="mt-1 opacity-90">{def.detail}</p>
        {def.tools.length > 0 && (
          <p className="mt-2 flex flex-wrap items-center gap-1 opacity-90">
            <Wrench className="size-3" aria-hidden />
            {def.tools.map((t) => (
              <code key={t} className="rounded bg-white/15 px-1">{t}</code>
            ))}
          </p>
        )}
        {line && <p className="mt-2 border-t border-white/20 pt-2">{line}</p>}
      </TooltipContent>
    </Tooltip>
  );
}

const nodeTypes = { agent: AgentNode };

export function AgentMap({ phase, active, state, steps, pending }: { phase: Phase; active: AgentId | null; state: AuditState; steps: Step[]; pending: Pending | null }) {
  // 세 건이 다 끝나면 총괄이 case를 비운다. 그때는 마지막 건의 모습을 그대로 둔다
  const cur = state.case ?? state.results?.at(-1)?.case ?? null;
  const { nodes, edges } = useMemo(() => {
    const mine = steps.filter((s) => s.case === cur);
    const doneOf = (id: AgentId) => mine.findLast((s) => s.agent === id && s.end);
    const order = CASES.findIndex((c) => c.key === cur);
    const lines: Partial<Record<AgentId, string>> = {
      총괄: phase === "done" ? "3건 모두 끝남" : cur ? `${order + 1}/3건째 · ${CASES[order]?.title}` : undefined,
      "문서 분석": doneOf("문서 분석") ? state.doc?.note : undefined,
      조사: doneOf("조사") ? state.claim : undefined,
      검증: doneOf("검증") ? `${state.verify?.pass ? "통과" : "기각"} · ${state.verify?.note ?? ""}` : undefined,
      감사: doneOf("감사") ? `숫자 ${state.audit?.numbers ?? 0}개 중 근거 없는 것 ${state.audit?.missing?.length ?? 0}개` : undefined,
      보고: doneOf("보고") && state.report?.case === cur ? `${state.report.recommendation} · ${state.report.reason}` : undefined,
      결재: pending ? "승인을 기다립니다" : state.results?.find((r) => r.case === cur)?.decision ?? undefined,
    };
    const statusOf = (id: AgentId): Status => {
      if (id === "결재" && phase === "waiting") return "waiting";
      if (phase === "running" && active === id) return "running";
      if (id === "검증" && doneOf("검증") && state.verify?.pass === false) return "rejected";
      if (id === "감사" && doneOf("감사") && state.audit?.pass === false) return "rejected";
      if ((id === "결재" || id === "보고") && doneOf("감사") && state.audit?.pass === false) return "skipped";
      if (doneOf(id)) return "done";
      return "idle";
    };
    // 총괄이 왼쪽 가운데, 위 줄은 왼쪽→오른쪽, 아래 줄은 오른쪽→왼쪽으로 돌아 총괄로 돌아오는 고리
    const POS: Record<AgentId, { x: number; y: number }> = {
      총괄: { x: 0, y: 100 }, "문서 분석": { x: 250, y: 0 }, 조사: { x: 500, y: 0 }, 검증: { x: 750, y: 0 },
      감사: { x: 750, y: 200 }, 보고: { x: 500, y: 200 }, 결재: { x: 250, y: 200 },
    };
    const nodes: Node<AgentNodeData>[] = AGENTS.map((def) => {
      const st = doneOf(def.id);
      return {
        id: def.id,
        type: "agent",
        position: POS[def.id],
        data: { def, status: statusOf(def.id), line: lines[def.id], sec: st?.end && def.id !== "결재" ? (st.end - st.start) / 1000 : undefined },
        draggable: false,
      };
    });
    // 방금 끝난 칸 → 지금 칸 연결선을 살린다
    const last = [...steps].reverse().find((s) => s.end && s.agent !== active);
    const liveFrom = phase === "running" && active ? last?.agent : undefined;
    const e = (source: AgentId, target: AgentId, extra: Partial<Edge> = {}): Edge => {
      const live = liveFrom === source && active === target;
      return { id: `${source}-${target}`, source, target, animated: live, className: live ? "is-live" : undefined, labelBgPadding: [6, 3], ...extra };
    };
    const edges: Edge[] = [
      e("총괄", "문서 분석", { sourceHandle: "r-s", targetHandle: "l-t" }),
      e("문서 분석", "조사", { sourceHandle: "r-s", targetHandle: "l-t" }),
      e("조사", "검증", { sourceHandle: "r-s", targetHandle: "l-t" }),
      e("검증", "감사", { sourceHandle: "bot-s", targetHandle: "top-t" }),
      e("감사", "보고", { sourceHandle: "l-s", targetHandle: "r-t", label: "통과" }),
      e("보고", "결재", { sourceHandle: "l-s", targetHandle: "r-t" }),
      e("결재", "총괄", { sourceHandle: "l-s", targetHandle: "bot-t", label: "다음 건" }),
      e("감사", "총괄", { type: "smoothstep", sourceHandle: "bot-s", targetHandle: "l-t", label: "기각되면 결재 없이 다음 건", pathOptions: { borderRadius: 10, offset: 30 } } as Partial<Edge>),
    ];
    return { nodes, edges };
  }, [phase, active, state, steps, pending, cur]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.06 }}
      nodesConnectable={false}
      elementsSelectable={false}
      panOnDrag={false}
      zoomOnScroll={false}
      zoomOnPinch={false}
      zoomOnDoubleClick={false}
      preventScrolling={false}
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={20} size={1} color="hsl(var(--border))" />
    </ReactFlow>
  );
}
