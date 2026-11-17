// 실행 기록: Langfuse에 쌓인 추적을 AgentPrism TraceViewer로 그린다.
import { langfuseSpanAdapter } from "@evilmartians/agent-prism-data";
import type { LangfuseDocument, TraceRecord } from "@evilmartians/agent-prism-types";
import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { TraceViewer, type TraceViewerData } from "@/components/agent-prism/TraceViewer/TraceViewer";
import { Button } from "@/components/ui/button";

type Row = { record: TraceRecord } & LangfuseDocument;

export function TracePanel({ refreshKey }: { refreshKey: number }) {
  const [data, setData] = useState<TraceViewerData[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const rows: Row[] = await (await fetch("/api/traces?limit=6")).json();
      setData(
        rows.map((r) => ({
          traceRecord: r.record,
          spans: langfuseSpanAdapter.convertRawDocumentsToSpans({ trace: r.trace, observations: r.observations } as LangfuseDocument),
        })),
      );
      setErr(null);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Langfuse가 기록을 받아 정리하는 데 몇 초 걸린다
    const id = setTimeout(load, refreshKey ? 6000 : 0);
    return () => clearTimeout(id);
  }, [load, refreshKey]);

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <h2 className="text-[15px] font-semibold">
            실행 기록 <span className="font-normal text-muted-foreground">(출처: Langfuse · AgentPrism)</span>
          </h2>
          <p className="text-xs text-muted-foreground">Langfuse가 남긴 추적입니다. 칸을 누르면 그 에이전트의 LLM 입력·출력·시간·토큰이 나옵니다.</p>
        </div>
        <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={loading ? "animate-spin" : ""} />
          새로 읽기
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden rounded-md border">
        {err && <p className="p-4 text-sm text-fail">기록을 읽지 못했습니다. Langfuse(3000)가 켜져 있는지 확인하세요.</p>}
        {!err && data && data.length === 0 && <p className="p-4 text-sm text-muted-foreground">아직 기록이 없습니다. 조사를 한 번 돌리면 여기에 쌓입니다.</p>}
        {!err && data && data.length > 0 && <TraceViewer key={data.map((d) => d.traceRecord.id).join()} data={data} />}
      </div>
    </div>
  );
}
