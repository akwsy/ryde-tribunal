import type { CaseResult } from "@/lib/api/types";
import { EvidenceControl } from "./evidence-control";
import { formatDateTime } from "@/lib/api/format";
import { activityLabel } from "@/lib/review-copy";
export function AgentTimeline({ result }: { result: CaseResult }) {
  return <details className="timeline-panel"><summary>Agent activity <span>{result.trace?.length ?? 0} recorded events</span></summary>
    {!result.trace?.length ? <p className="p-5 text-sm text-slate-600">No agent trace was recorded for this historical example.</p> : <ol className="timeline-list">{result.trace.map((item,index) => <li key={`${item.at}-${index}`}>
      <div className="flex flex-wrap justify-between gap-2"><strong className="capitalize">{item.actor.replaceAll("_", " ")}</strong><time className="text-xs text-slate-500">{formatDateTime(item.at)}</time></div>
      <p className="mt-1 text-sm text-slate-700">{activityLabel(item.event)}</p>
      <details className="mt-2 text-xs text-slate-500"><summary className="cursor-pointer">Details of this step</summary><p className="mt-2">{item.summary}</p><p className="mt-1">Event: {item.event}</p></details>
      {item.evidence_ids.length > 0 && <div className="mt-2 grid gap-2 sm:grid-cols-2">{item.evidence_ids.map((evidenceId) => <EvidenceControl key={evidenceId} evidenceId={evidenceId} caseId={result.case_id} title="Evidence used in this step" />)}</div>}
      {item.provider && <details className="mt-2 text-xs text-slate-500"><summary className="cursor-pointer">Technical details</summary><p className="mt-1">Provider: {item.provider}</p></details>}
    </li>)}</ol>}
  </details>;
}
