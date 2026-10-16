import { PolicyReference } from "./policy-reference";
import { SyntheticBadge } from "./synthetic-badge";
import { EvidenceControl } from "./evidence-control";
import { factValue, fieldLabel } from "@/lib/review-copy";
import type { AdvocateOutput } from "@/lib/api/types";

export function AdvocatePanel({ role, advocate, caseId, syntheticReasoning, policyVersion }: {
  role: "rider" | "driver"; advocate: AdvocateOutput; caseId: string; syntheticReasoning: boolean;
  side: "left" | "right"; policyVersion?: string;
}) {
  const rider = role === "rider";
  const claims = advocate.claims;
  function claimCard(claim: AdvocateOutput["claims"][number], index: number) {
    const primary = claim.citations[0];
    return <li key={index} className="claim-card">
      <p className="text-sm font-medium text-slate-800">{primary ? `${fieldLabel(primary.field_path)}: ${factValue(primary.field_path, primary.observed_value)}` : claim.text}</p><details className="mt-2 text-xs text-slate-500"><summary className="cursor-pointer">Original claim</summary><p className="mt-2">{claim.text}</p></details>
      <div className="claim-evidence-list" aria-label={`Evidence for claim ${index + 1}`}>{claim.citations.map(citation => <div key={`${citation.evidence_id}-${citation.field_path}`}>
        <EvidenceControl evidenceId={citation.evidence_id} caseId={caseId} title={fieldLabel(citation.field_path)}
          summary={factValue(citation.field_path, citation.observed_value)} citedField={citation.field_path} observedValue={citation.observed_value} />
        <span className={`citation-state ${citation.valid ? "valid" : "invalid"}`}>{citation.valid ? "Source checked" : "Citation needs review"}</span>
      </div>)}</div>
    </li>;
  }
  return <section className="rounded-2xl border border-slate-200 bg-white p-5 md:p-6" aria-label={rider ? "Rider Advocate" : "Driver Advocate"} data-testid={`advocate-panel-${role}`}>
    <header className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <div><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{rider ? "Rider Advocate" : "Driver Advocate"}</p><h2 className="mt-1 text-lg font-semibold text-slate-900">{rider ? "The rider’s case" : "The driver’s case"}</h2></div>
      {advocate.provider.kind === "rules-engine" && <span className="text-xs text-teal-800">Rules-based review</span>}<SyntheticBadge show={syntheticReasoning || advocate.provider.kind === "deterministic-mock"} size="sm" />
    </header>
    <h3 className="mb-3 text-sm font-medium text-slate-600">Key supporting evidence</h3>
    {claims.length ? <ol className="space-y-3">{claims.slice(0, 3).map(claimCard)}</ol> : <p className="text-sm text-slate-600">No verified supporting facts were recorded for this position.</p>}
    {advocate.invalid_citation_count > 0 && <p role="status" className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{advocate.invalid_citation_count} evidence reference(s) need review. Unsupported claims must not determine the outcome.</p>}
    <details className="mt-4 border-t border-slate-100 pt-4"><summary className="cursor-pointer text-sm font-semibold text-teal-800">Read the full argument{claims.length > 3 ? ` and ${claims.length - 3} more facts` : ""}</summary>
      <p className="my-4 text-sm leading-relaxed text-slate-700">{advocate.argument}</p>
      <ol className="space-y-3">{claims.slice(3).map((claim, i) => claimCard(claim, i + 3))}</ol>
    </details>
    {advocate.policy_references.length > 0 && <div className="mt-4 flex flex-wrap gap-2">{advocate.policy_references.map(id => <PolicyReference key={id} ruleId={id} version={policyVersion} />)}</div>}
    {!!advocate.rejected_evidence?.length && <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold text-amber-900">Evidence not relied on ({advocate.rejected_evidence.length})</summary><ul className="mt-3 space-y-3">{advocate.rejected_evidence.map((item, i) => <li key={i}><p className="mb-2 text-sm">{item.reason}</p><EvidenceControl evidenceId={item.evidence_id} caseId={caseId} title="Evidence not relied on" /></li>)}</ul></details>}
    <details className="agent-technical-details mt-4"><summary>Agent details</summary><dl><div><dt>Reasoning provider</dt><dd>{advocate.provider.display_name ?? advocate.provider.kind}</dd></div><div><dt>Invalid citations</dt><dd>{advocate.invalid_citation_count}</dd></div></dl></details>
  </section>;
}
