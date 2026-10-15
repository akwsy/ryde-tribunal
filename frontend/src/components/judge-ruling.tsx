import { PolicyReference } from "./policy-reference";
import type { JudgeOutput, CaseResult } from "@/lib/api/types";
import { SyntheticBadge } from "./synthetic-badge";
import { MoneyDisplay } from "./money-display";
import { EvidenceControl } from "./evidence-control";
import {
  formatConfidence,
  formatConfidenceA11y,
  labelForRulingType,
  formatDateTime,
} from "@/lib/api/format";

/**
 * Judge ruling panel — renders the recommended action (with money formatted
 * from amount_cents + currency), confidence (as percentage with raw float
 * in aria-label), reasoning, evidence references, policy references,
 * precedent references, and measurements.
 *
 * The synthetic badge is shown when the judge's provider is deterministic-mock
 * or when the case-level synthetic_reasoning flag is true.
 *
 * Escalation state is rendered by the EscalationState component, which is
 * branched on judge.escalation.escalated — never on comparing confidence
 * to a threshold.
 */
export function JudgeRuling({
  judge,
  caseResult,
}: {
  judge: JudgeOutput;
  caseResult: CaseResult;
}) {
  const providerIsMock = judge.provider.kind === "deterministic-mock";
  const showBadge = caseResult.synthetic_reasoning || providerIsMock;
  const isEscalated = judge.escalation.escalated;

  return (
    <section
      className="flex flex-col gap-4 rounded-xl border-2 border-tribunal-judge/30 bg-white p-5"
      aria-label="Judge Ruling"
      data-testid="judge-ruling"
    >
      <header className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-tribunal-judge">Judge Ruling</h2>
        <div className="flex items-center gap-2">
          {showBadge && <SyntheticBadge show={true} size="sm" />}
          {judge.provider.kind === "rules-engine" && <span className="rounded-full bg-teal-50 px-2 py-1 text-xs font-medium text-teal-800">Rules-based decision</span>}
          {judge.provider.kind === "llm" && <span className="rounded-full bg-blue-50 px-2 py-1 text-xs font-medium text-blue-800">AI reviewed</span>}
        </div>
      </header>

      {/* Ruling type */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-1">Ruling</h3>
        <p className="text-xl font-bold text-gray-900">
          {labelForRulingType(judge.ruling_type)}
        </p>
      </div>

      {/* Recommended action */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-1">Recommended Action</h3>
        <p className="text-sm text-gray-900 mb-2">{judge.recommended_action.description}</p>
        {judge.recommended_action.amount && (
          <MoneyDisplay money={judge.recommended_action.amount} size="lg" />
        )}
      </div>

      {judge.recommended_action.delivery === "voucher" && <p className="rounded-lg bg-teal-50 p-3 text-sm text-teal-900">Voucher waiver recommendation · Not a cash refund</p>}
      {/* Confidence */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-1">Confidence</h3>
        <div
          className="flex items-baseline gap-2"
          aria-label={formatConfidenceA11y(judge.confidence)}
          data-testid="confidence-display"
        >
          <span className="text-3xl font-bold text-gray-900" data-confidence-value={judge.confidence}>
            {formatConfidence(judge.confidence)}
          </span>
          {isEscalated && (
            <span className="text-sm font-medium text-tribunal-escalation">
              ↑ Escalated
            </span>
          )}
        </div>
      </div>

      {/* Reasoning */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-1">Reasoning</h3>
        <p className="text-sm text-gray-900 leading-relaxed">{judge.reasoning}</p>
      </div>

      {judge.decisive_facts.length > 0 && <section aria-label="Decisive facts"><h3 className="mb-2 text-sm font-semibold text-gray-700">Key facts behind the decision</h3><ul className="space-y-3">{judge.decisive_facts.map((fact,index) => <li key={index} className="claim-card"><p className="text-sm">{fact.fact}</p>{fact.citations?.map((citation) => <div key={`${citation.evidence_id}-${citation.field_path}`} className="mt-3"><EvidenceControl evidenceId={citation.evidence_id} caseId={caseResult.case_id} title={citation.field_path.split(".").at(-1)?.replaceAll("_", " ") ?? "Supporting record"} citedField={citation.field_path} observedValue={citation.observed_value} summary={formatCitedFact(citation.field_path, citation.observed_value)} /><span className={`citation-state ${citation.valid ? "valid" : "invalid"}`}>{citation.valid ? "Source checked" : "Citation needs review"}</span></div>)}</li>)}</ul></section>}
      {/* Measurements */}
      {judge.measurements && Object.keys(judge.measurements).length > 0 && (
        <details className="agent-technical-details">
          <summary>Technical measurements</summary>
          <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
            {Object.entries(judge.measurements).map(([key, value]) => (
              <div key={key}>
                <dt className="font-mono text-xs text-gray-500">{key.replaceAll("_", " ")}</dt>
                <dd className="font-mono text-gray-900">
                  {typeof value === "boolean"
                    ? value
                      ? "Yes"
                      : "No"
                    : value}
                </dd>
              </div>
            ))}
          </dl>
        </details>
      )}

      {/* Evidence references */}
      {judge.evidence_references.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Supporting records</h3>
          <div className="flex flex-col gap-2">
            {judge.evidence_references.map((eid) => (
              <EvidenceControl key={eid} evidenceId={eid} caseId={caseResult.case_id} title="Supporting record" />
            ))}
          </div>
        </div>
      )}

      {/* Policy references */}
      {judge.policy_references.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-1">Policy References</h3>
          <div className="flex flex-wrap gap-1.5">
            {judge.policy_references.map((ref) => (
              <PolicyReference key={ref} ruleId={ref} version={caseResult.policy_version} />
            ))}
          </div>
        </div>
      )}

      {/* Precedent references */}
      {judge.precedent_references && judge.precedent_references.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-1">
            Precedent References
            {!judge.precedent_binding && (
              <span className="ml-2 text-xs font-normal text-gray-500">(advisory, non-binding)</span>
            )}
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {judge.precedent_references.map((ref) => (
              <span
                key={ref}
                className="inline-block rounded bg-gray-100 border border-gray-300 px-2 py-0.5 text-xs font-mono text-gray-700"
              >
                {ref}
              </span>
            ))}
          </div>
        </div>
      )}

      <details className="agent-technical-details">
        <summary>Judge details</summary>
        <dl><div><dt>Reasoning provider</dt><dd>{judge.provider.display_name ?? (providerIsMock ? "Local deterministic" : "Not supplied")}</dd></div>
          <div><dt>Provider type</dt><dd>{providerIsMock ? "Scripted fallback" : "Live model"}</dd></div></dl>
      </details>
    </section>
  );
}

function formatCitedFact(path: string, value: unknown): string {
  const key = path.split(".").at(-1) ?? path;
  if (value === null || value === undefined) return "Value not available";
  if (key.endsWith("_cents")) return new Intl.NumberFormat("en-SG", { style: "currency", currency: "SGD" }).format(Number(value) / 100);
  if (key.endsWith("_km")) return `${value} km`;
  if (key.endsWith("_m")) return `${value} m`;
  if (key.endsWith("_pct")) return `${value}%`;
  if (key === "driver_waited_seconds") return `${Math.round(Number(value) / 60)} min`;
  if (key === "latitude" || key === "longitude") return "Pin on map";
  if (typeof value === "boolean") return value ? "Recorded" : "Not recorded";
  return String(value);
}
