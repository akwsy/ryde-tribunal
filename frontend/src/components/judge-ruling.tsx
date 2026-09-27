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
        {showBadge && <SyntheticBadge show={true} size="sm" />}
      </header>

      {/* Provider info */}
      <p className="text-xs text-gray-500">
        Provider: <span>{judge.provider.display_name ?? (providerIsMock ? "local deterministic" : "Unknown provider")}</span>
      </p>

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

      {/* Measurements */}
      {judge.measurements && Object.keys(judge.measurements).length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-1">Measurements</h3>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            {Object.entries(judge.measurements).map(([key, value]) => (
              <div key={key}>
                <dt className="font-mono text-xs text-gray-500">{key}</dt>
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
        </div>
      )}

      {/* Evidence references */}
      {judge.evidence_references.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Evidence References</h3>
          <div className="flex flex-col gap-2">
            {judge.evidence_references.map((eid) => (
              <EvidenceControl key={eid} evidenceId={eid} caseId={caseResult.case_id} />
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
              <span
                key={ref}
                className="inline-block rounded bg-purple-50 border border-purple-200 px-2 py-0.5 text-xs font-mono text-purple-800"
              >
                {ref}
              </span>
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
    </section>
  );
}
