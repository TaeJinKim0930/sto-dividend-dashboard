// 결재 보고서 팝업. 에이전트 팀이 결재권자에게 올리는 보고서 형식으로 보여 준다.
import { AlertTriangle, CheckCircle2, CircleHelp, FileText, Gavel } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { AGENTS } from "./agents";
import type { Report, Step } from "./useAudit";

function Section({ n, title, source, children }: { n: number; title: string; source?: string; children: ReactNode }) {
  return (
    <section className="border-t pt-4">
      <h3 className="text-sm font-semibold">
        {n}. {title}
        {source && <span className="ml-1.5 font-normal text-muted-foreground">(출처: {source})</span>}
      </h3>
      <div className="mt-2">{children}</div>
    </section>
  );
}

const fmt = (v: unknown) => (typeof v === "number" ? v.toLocaleString("ko-KR") : v == null ? "–" : String(v));

export function ReportDialog({ report, steps, decide, canDecide }: { report: Report; steps: Step[]; decide: (d: "승인" | "반려") => void; canDecide: boolean }) {
  const [open, setOpen] = useState(false);
  const [checked, setChecked] = useState<Record<number, boolean>>({});
  const reject = report.recommendation === "반려 권고";
  const mine = steps.filter((s) => s.case === report.case && s.end && s.agent !== "결재");
  const todo = report.checklist.filter((c) => c.level !== "ok");
  const doneCount = todo.filter((c) => checked[report.checklist.indexOf(c)]).length;
  const go = (d: "승인" | "반려") => {
    setOpen(false);
    decide(d);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="secondary" className="w-full">
          <FileText />
          보고서 자세히 보기
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] max-w-4xl gap-0 overflow-y-auto p-0">
        <DialogHeader className="space-y-1 px-6 pb-4 pt-6 text-left">
          <p className="text-xs text-muted-foreground">
            결재 보고서 <span className="ml-1">(출처: 보고 에이전트 · Ollama gemma4 · shadcn/ui Dialog)</span>
          </p>
          <DialogTitle className="text-xl">{report.title}</DialogTitle>
          <DialogDescription>
            보고: 에이전트 조사팀 (문서 분석 → 조사 → 검증 → 감사 → 보고) · 받는 분: 결재권자 · {new Date().toLocaleString("ko-KR")}
          </DialogDescription>
        </DialogHeader>

        <div className={cn("mx-6 flex items-start gap-3 rounded-md border p-4", reject ? "border-fail/40 bg-fail/5" : "border-pass/40 bg-pass/5")}>
          {reject ? <AlertTriangle className="mt-0.5 size-5 shrink-0 text-fail" /> : <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-pass" />}
          <div>
            <p className={cn("text-base font-semibold", reject ? "text-fail" : "text-pass")}>{report.recommendation}</p>
            <p className="text-sm">{report.reason}. 권고는 코드가 숫자 대조 결과로 정했고, 최종 결정은 결재권자가 합니다.</p>
          </div>
        </div>

        <div className="space-y-5 px-6 py-5">
          <Section n={1} title="보고 요지" source="보고 에이전트 LLM">
            <p className="text-sm leading-relaxed">{report.summary}</p>
            <blockquote className="mt-3 border-l-2 pl-3 text-sm text-muted-foreground">
              <span className="text-xs font-medium text-foreground">조사관이 쓴 원래 주장</span>
              <br />
              {report.claim}
            </blockquote>
          </Section>

          <Section n={2} title="결재권자가 판단·확인할 것" source="보고 에이전트 (코드 + LLM)">
            <ul className="space-y-2">
              {report.checklist.map((c, i) => (
                <li key={i} className="flex items-start gap-3 text-sm">
                  {c.level === "ok" ? (
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-pass" aria-label="이미 확인됨" />
                  ) : (
                    <input
                      type="checkbox"
                      className="mt-1 size-4 shrink-0 accent-[hsl(var(--primary))]"
                      checked={!!checked[i]}
                      onChange={(e) => setChecked((m) => ({ ...m, [i]: e.target.checked }))}
                      aria-label={`${c.item} 확인`}
                    />
                  )}
                  <div>
                    <span className={cn("font-medium", c.level === "decide" && "text-wait")}>
                      {c.level === "decide" && <Gavel className="mr-1 inline size-3.5 align-[-2px]" />}
                      {c.item}
                    </span>
                    <span className="ml-2 text-muted-foreground">{c.detail}</span>
                  </div>
                </li>
              ))}
            </ul>
          </Section>

          <Section n={3} title="숫자 대조표: 주장 속 숫자는 원래 무슨 뜻인가" source="map_numbers 코드 + LLM 뜻 검사">
            <p className="mb-2 text-xs text-muted-foreground">
              감사의 근거 인용 검사는 숫자가 도구 결과에 있는지만 봅니다. 이 표는 그 숫자가 원래 어느 칸의 무슨 뜻인지까지 대조합니다.
            </p>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-1.5 pr-3 font-normal">숫자</th>
                  <th className="py-1.5 pr-3 font-normal">주장 문장에서 쓴 뜻</th>
                  <th className="py-1.5 pr-3 font-normal">실제 데이터의 뜻</th>
                  <th className="py-1.5 pr-3 font-normal">나온 곳</th>
                  <th className="py-1.5 font-normal">판정</th>
                </tr>
              </thead>
              <tbody>
                {report.numbers.map((r) => (
                  <tr key={r.number} className={cn("border-b align-top last:border-b-0", !r.ok && "bg-fail/5")}>
                    <td className="py-2 pr-3 font-semibold tabular-nums">{r.number}</td>
                    <td className="py-2 pr-3">{r.claim_usage ?? "–"}</td>
                    <td className="py-2 pr-3">{r.meaning}</td>
                    <td className="py-2 pr-3 text-xs text-muted-foreground">
                      {r.tool_ko ?? "–"}
                      {r.source && <code className="block">{r.source}</code>}
                    </td>
                    <td className={cn("py-2 font-medium", r.ok ? "text-pass" : "text-fail")} title={r.why ?? undefined}>
                      {r.ok ? "일치" : "불일치"}
                      {!r.ok && r.why && <span className="block text-xs font-normal text-muted-foreground">{r.why}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section n={4} title="독립 재계산 대조" source="검증 에이전트 · recompute 도구">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-1.5 pr-3 font-normal">항목</th>
                  <th className="py-1.5 pr-3 text-right font-normal">조사 값</th>
                  <th className="py-1.5 pr-3 text-right font-normal">다시 계산한 값</th>
                  <th className="py-1.5 font-normal">결과</th>
                </tr>
              </thead>
              <tbody>
                {report.recompute.map((r) => (
                  <tr key={r.item} className="border-b last:border-b-0">
                    <td className="py-2 pr-3">{r.item}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{fmt(r.investigation)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{fmt(r.recompute)}</td>
                    <td className={cn("py-2 font-medium", r.match ? "text-pass" : "text-fail")}>{r.match ? "일치" : "다름"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-muted-foreground">검증 의견: {report.verify_note}</p>
          </Section>

          <Section n={5} title="투자설명서 근거" source="문서 분석 에이전트 · SEC 485BPOS 원문">
            <p className="text-sm">{report.doc.note}</p>
            <ul className="mt-2 space-y-2">
              {report.doc.hits.map((h) => (
                <li key={h.sentence_no} className="rounded-md bg-muted p-3 text-xs leading-relaxed">
                  <span className="font-medium">원문 {h.sentence_no}번 문장</span>
                  <p className="mt-1 text-muted-foreground" lang="en">{h.text}</p>
                </li>
              ))}
            </ul>
            <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
              <CircleHelp className="size-3.5" /> 검색어 “{report.doc.query}”로 찾은 문장입니다. 주제와 실제로 관련 있는지는 사람이 봐야 합니다.
            </p>
          </Section>

          <Section n={6} title="처리 경위" source="AG-UI 단계 이벤트 · Langfuse">
            <ol className="space-y-1 text-sm">
              {mine.map((s, i) => (
                <li key={i} className="flex gap-3">
                  <span className="w-16 shrink-0 font-medium">{s.agent}</span>
                  <span className="flex-1 text-muted-foreground">{AGENTS.find((a) => a.id === s.agent)?.role}</span>
                  <span className="tabular-nums text-muted-foreground">{((s.end! - s.start) / 1000).toFixed(1)}초</span>
                </li>
              ))}
            </ol>
            <p className="mt-2 text-xs text-muted-foreground">각 단계의 LLM 입력·출력은 아래 실행 기록에서 볼 수 있습니다. 감사 의견: {report.audit_note}</p>
          </Section>
        </div>

        <div className="sticky bottom-0 flex items-center gap-3 border-t bg-background px-6 py-4">
          <span className="text-xs text-muted-foreground">
            확인 사항 {doneCount} / {todo.length}
          </span>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" disabled={!canDecide} onClick={() => go("반려")}>
              반려
            </Button>
            <Button disabled={!canDecide} onClick={() => go("승인")}>
              승인
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
