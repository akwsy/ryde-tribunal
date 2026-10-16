import { PolicyReference } from "./policy-reference";
import type { JudgeOutput, CaseResult } from "@/lib/api/types";
import { SyntheticBadge } from "./synthetic-badge";
import { EvidenceControl } from "./evidence-control";
import { formatConfidence, formatConfidenceA11y } from "@/lib/api/format";
import { fieldLabel, factValue } from "@/lib/review-copy";

export function JudgeRuling({ judge, caseResult }: { judge: JudgeOutput; caseResult: CaseResult }) {
  const review = judge.escalation.escalated && !caseResult.reviewer_approved_ruling;
  const facts = judge.decisive_facts;
  function factCard(fact: JudgeOutput["decisive_facts"][number], index: number) {
    return <li key={index} className="claim-card"><p className="text-sm leading-relaxed text-slate-800">{fact.citations?.[0] ? `${fieldLabel(fact.citations[0].field_path)}: ${factValue(fact.citations[0].field_path, fact.citations[0].observed_value)}` : fact.fact}</p>
      {fact.citations?.map(citation => <div key={`${citation.evidence_id}-${citation.field_path}`} className="mt-3"><EvidenceControl evidenceId={citation.evidence_id} caseId={caseResult.case_id}
        title={fieldLabel(citation.field_path)} summary={factValue(citation.field_path, citation.observed_value)} citedField={citation.field_path} observedValue={citation.observed_value} />
        <span className={`citation-state ${citation.valid ? "valid" : "invalid"}`}>{citation.valid ? "Source checked" : "Citation needs review"}</span></div>)}
      {!fact.citations?.length && fact.evidence_references.map(id => <EvidenceControl key={id} evidenceId={id} caseId={caseResult.case_id} title="Supporting record" />)}
    </li>;
  }
  return <section className="rounded-2xl border border-slate-200 bg-white p-5 md:p-6" aria-label="Judge Ruling" data-testid="judge-ruling">
    <header className="flex flex-wrap justify-between gap-3"><h2 className="text-lg font-semibold text-slate-900">{review ? "What needs a reviewer’s attention" : "Why this outcome"}</h2>
      <div className="flex items-center gap-2"><SyntheticBadge show={caseResult.synthetic_reasoning || judge.provider.kind === "deterministic-mock"} size="sm" />
        <span className="text-xs text-slate-500">{judge.provider.kind === "rules-engine" ? "Rules-based decision" : judge.provider.kind === "llm" ? "AI reviewed" : "Scripted fallback"}</span></div></header>
    {facts.length ? <ul className="mt-4 space-y-3" aria-label="Decisive facts">{facts.slice(0, 3).map(factCard)}</ul> : <p className="mt-3 text-sm leading-relaxed text-slate-700">The available records do not support a final decision. Check the unresolved evidence or policy questions before recording an outcome.</p>}
    <div className="mt-4 flex flex-wrap items-center gap-2">{judge.policy_references.map(id => <PolicyReference key={id} ruleId={id} version={caseResult.policy_version} />)}</div>
    <details className="mt-4 border-t border-slate-100 pt-4"><summary className="cursor-pointer text-sm font-semibold text-teal-800">Read the full assessment</summary>
      <p className="my-3 text-sm leading-relaxed text-slate-700">{judge.reasoning}</p>
      {facts.length > 3 && <ul className="space-y-3">{facts.slice(3).map((fact, i) => factCard(fact, i + 3))}</ul>}
      {!!judge.evidence_references.length && <details className="mt-4"><summary className="cursor-pointer text-sm font-medium">All supporting records ({judge.evidence_references.length})</summary><div className="mt-3 space-y-2">{judge.evidence_references.map(id => <EvidenceControl key={id} evidenceId={id} caseId={caseResult.case_id} title="Supporting record" />)}</div></details>}
      <div className="mt-4 text-sm text-slate-600" aria-label={formatConfidenceA11y(judge.confidence)} data-testid="confidence-display">Decision confidence: <span data-confidence-value={judge.confidence}>{formatConfidence(judge.confidence)}</span>{review && <span> · Human review required</span>}</div>
    </details>
    <details className="agent-technical-details mt-4"><summary>Technical details</summary>
      <dl className="mt-3 grid gap-2">{Object.entries(judge.measurements ?? {}).map(([key, value]) => <div key={key}><dt>{fieldLabel(key)}</dt><dd>{typeof value === "boolean" ? value ? "Yes" : "No" : factValue(key, value)}</dd></div>)}
      <div><dt>Reasoning provider</dt><dd>{judge.provider.display_name ?? judge.provider.kind}</dd></div><div><dt>Provider type</dt><dd>{judge.provider.kind === "rules-engine" ? "Rules engine" : judge.provider.kind === "llm" ? "Live model" : "Scripted fallback"}</dd></div></dl>
      {!!judge.precedent_references?.length && <p className="mt-3 text-xs">Advisory past cases: {judge.precedent_references.join(", ")}. Past cases do not override current policy.</p>}
    </details>
  </section>;
}
