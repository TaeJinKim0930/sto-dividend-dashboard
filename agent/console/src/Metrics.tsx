// 지표: GPU 사용률 흐름과 에이전트별 소요 시간 (Recharts).
import { useEffect, useState } from "react";
import { Area, AreaChart, Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AGENTS } from "./agents";
import type { Step } from "./useAudit";

export type MetricsSample = { t: number; util: number; mem: number };
export type MetricsNow = { gpu: { util?: number; mem_used?: number; mem_total?: number; temp?: number }; models: string[]; model: string };

export function useMetrics() {
  const [series, setSeries] = useState<MetricsSample[]>([]);
  const [now, setNow] = useState<MetricsNow | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const m = await (await fetch("/api/metrics")).json();
        if (!alive) return;
        setNow(m);
        setSeries((s) => [...s.slice(-89), { t: m.t * 1000, util: m.gpu.util ?? 0, mem: (m.gpu.mem_used ?? 0) / 1024 }]);
      } catch {
        /* 백엔드가 꺼져 있으면 다음 차례에 다시 */
      }
    };
    void tick();
    const id = setInterval(tick, 2000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);
  return { series, now };
}

const tip = {
  contentStyle: { background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 12 },
  labelStyle: { color: "hsl(var(--muted-foreground))" },
};

export function GpuChart({ series }: { series: MetricsSample[] }) {
  return (
    <ResponsiveContainer width="100%" height={130}>
      <AreaChart data={series} margin={{ top: 6, right: 4, bottom: 0, left: -18 }}>
        <defs>
          <linearGradient id="gpuFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(var(--chart-1))" stopOpacity={0.35} />
            <stop offset="100%" stopColor="hsl(var(--chart-1))" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="t" hide />
        <YAxis domain={[0, 100]} ticks={[0, 50, 100]} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} unit="%" />
        <Tooltip {...tip} labelFormatter={(t) => new Date(Number(t)).toLocaleTimeString("ko-KR")} formatter={(v) => [`${v}%`, "GPU 사용률"]} />
        <Area type="monotone" dataKey="util" stroke="hsl(var(--chart-1))" strokeWidth={1.5} fill="url(#gpuFill)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function AgentTimeChart({ steps }: { steps: Step[] }) {
  const data = AGENTS.filter((a) => !a.human).map((a) => ({
    name: a.id,
    sec: Math.round(steps.filter((s) => s.agent === a.id && s.end).reduce((t, s) => t + (s.end! - s.start), 0) / 100) / 10,
  }));
  return (
    <ResponsiveContainer width="100%" height={150}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 30, bottom: 0, left: 8 }} barSize={12}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="name" width={72} tick={{ fontSize: 12, fill: "hsl(var(--foreground))" }} axisLine={false} tickLine={false} />
        <Tooltip {...tip} cursor={{ fill: "hsl(var(--muted))" }} formatter={(v) => [`${v}초`, "합계"]} />
        <Bar dataKey="sec" fill="hsl(var(--chart-1))" radius={[0, 3, 3, 0]} isAnimationActive={false} label={{ position: "right", fontSize: 11, fill: "hsl(var(--muted-foreground))", formatter: (v: unknown) => (Number(v) ? `${v}초` : "") }} />
      </BarChart>
    </ResponsiveContainer>
  );
}
