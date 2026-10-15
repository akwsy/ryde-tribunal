import type { CaseResult } from "@/lib/api/types";
import { formatConfidence } from "@/lib/api/format";
import { EvidenceControl } from "./evidence-control";

const concernLabels: Record<string, string> = {
  contradicted: "Conflicting with the trip record",
  incorrect: "Does not match the source record",
  fabrication_suspected: "Could not be verified",
  unsupported: "Missing supporting record",
  inconclusive: "Needs a closer look",
};

export function EvidenceReviewSummary({ result }: { result: CaseResult }) {
  const audit = result.evidence_audit;
  const citations = (["rider", "driver"] as const).flatMap((party) =>
    result.advocates?.[party]?.claims.flatMap((claim) => claim.citations) ?? [],
  );
  const invalidCitations = citations.filter((citation) => !citation.valid);
  const concerns = audit?.findings.filter((finding) =>
    finding.classification !== "consistent" && finding.materiality !== "non_material",
  ) ?? [];
  const needsAttention = invalidCitations.length > 0 || concerns.length > 0;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5" aria-label="Judge evidence review" data-testid="judge-evidence-review">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-slate-900">Judge’s evidence check</h2>
          <p className="mt-1 text-sm text-slate-600">
            {audit
              ? needsAttention
                ? "The judge has been shown evidence issues that may affect the decision."
                : "The cited records were checked before the judge prepared a recommendation."
              : result.status === "processing"
                ? "Checking that each claim matches a record from this trip…"
                : result.case_source === "archive"
                  ? "This historical record does not include the agent evidence check."
                  : "This check runs after both sides present their evidence."}
          </p>
        </div>
        <span className={statusClass(Boolean(audit), needsAttention)}>
          {audit ? needsAttention ? "Needs attention" : "Checked" : result.case_source === "archive" ? "Not recorded" : result.status === "processing" ? "In progress" : "Not started"}
        </span>
      </header>

      {audit && <p className="mt-3 text-sm text-slate-700">
        {invalidCitations.length === 0
          ? citations.length + " evidence citation" + (citations.length === 1 ? "" : "s") + " checked against the case records."
          : invalidCitations.length + " of " + citations.length + " evidence citations need review."}
        {concerns.length > 0 && " " + concerns.length + " claim concern" + (concerns.length === 1 ? "" : "s") + " flagged."}
      </p>}

      {audit && <details className="agent-technical-details mt-4">
        <summary>View evidence check details</summary>
        <p className="mt-3 text-xs text-slate-500">Checked by {audit.provider.display_name ?? "the evidence review agent"}.</p>
        <ul className="mt-3 space-y-3">
          {invalidCitations.map((citation, index) => (
            <li key={citation.evidence_id + "-" + index} className="rounded-lg border border-amber-200 bg-amber-50 p-3">
              <p className="text-sm font-medium text-amber-950">Citation could not be confirmed</p>
              <EvidenceControl evidenceId={citation.evidence_id} caseId={result.case_id} title="Cited trip record" citedField={citation.field_path} summary="Open the record to check this claim." />
            </li>
          ))}
          {concerns.map((finding, index) => (
            <li key={finding.party + "-" + index} className="rounded-lg border border-slate-200 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{finding.party === "rider" ? "Rider’s case" : "Driver’s case"} · {finding.classification.replaceAll("_", " ")} · {formatConfidence(finding.confidence)} confidence</p>
              <p className="mt-1 text-sm font-medium text-slate-900">{finding.claim_text}</p>
              <p className="mt-1 text-sm font-medium text-slate-900">{concernLabels[finding.classification] ?? "Evidence concern"}</p>
              <p className="mt-1 text-sm text-slate-700">{finding.explanation}</p>
              {finding.evidence_references.map((evidenceId) => <EvidenceControl key={evidenceId} evidenceId={evidenceId} caseId={result.case_id} title="Supporting record" />)}
            </li>
          ))}
          {invalidCitations.length === 0 && concerns.length === 0 && <li className="text-sm text-slate-600">No citation or claim concerns were found.</li>}
        </ul>
      </details>}
    </section>
  );
}

function statusClass(checked: boolean, needsAttention: boolean): string {
  const color = !checked ? "bg-slate-100 text-slate-700" : needsAttention ? "bg-amber-100 text-amber-900" : "bg-green-100 text-green-900";
  return "rounded-full px-3 py-1 text-xs font-semibold " + color;
}
