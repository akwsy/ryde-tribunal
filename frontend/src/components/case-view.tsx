"use client";

import { useState, useEffect, useCallback } from "react";
import type { CaseResult } from "@/lib/api/types";
import { getActiveClient } from "@/lib/api/fixture-client";
import { ApiError } from "@/lib/api/client";
import { CaseDetails } from "./case-details";
import { ReviewerActions } from "./reviewer-actions";
import { AdvocatePanel } from "./advocate-panel";
import { JudgeRuling } from "./judge-ruling";
import { EscalationState } from "./escalation-state";
import { EvidenceControl } from "./evidence-control";
import { LoadingState, EmptyState, ErrorState } from "./state-surfaces";
import { formatConfidence, formatConfidenceA11y } from "@/lib/api/format";

/**
 * The case view orchestrator.
 *
 * Fetches GET /api/v1/disputes/{case_id} and renders the full case result:
 * - Case details (header)
 * - Rider Advocate (left) and Driver Advocate (right), on opposite sides
 * - Judge ruling with recommended action, confidence, reasoning
 * - Clickable evidence controls that reveal the underlying record
 * - Per-evidence verification status and uncertainty percentage
 * - Escalation state with human-review summary
 *
 * Loading, empty, error, and escalated are first-class render paths.
 */
export function CaseView({ caseId }: { caseId: string }) {
  const [caseResult, setCaseResult] = useState<CaseResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ code: string; message: string; status: number } | null>(null);

  const fetchCase = useCallback(async () => {
    setLoading(true);
    setError(null);
    setCaseResult(null);

    try {
      const client = getActiveClient();
      const result = await client.getDispute(caseId);
      setCaseResult(result);
    } catch (e) {
      if (e instanceof ApiError) {
        setError({ code: e.code, message: e.message, status: e.status });
      } else {
        setError({
          code: "internal_error",
          message: e instanceof Error ? e.message : "An unexpected error occurred.",
          status: 500,
        });
      }
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    fetchCase();
  }, [fetchCase]);

  if (loading) {
    return <LoadingState caseId={caseId} />;
  }

  if (error) {
    if (error.code === "not_found") {
      return <EmptyState caseId={caseId} />;
    }
    return (
      <ErrorState
        caseId={caseId}
        code={error.code}
        message={error.message}
        status={error.status}
      />
    );
  }

  if (!caseResult) {
    // Defensive: should not reach here, but handles all paths.
    return (
      <ErrorState
        caseId={caseId}
        code="internal_error"
        message="No case data was returned."
        status={500}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto p-4 md:p-6">
      {caseResult.case_source === "archive" && (
        <section className="rounded-xl border border-slate-300 bg-slate-50 p-4" aria-label="Historical read-only record" data-testid="historical-read-only">
          <h2 className="font-semibold text-slate-900">Historical record · read only</h2>
          <p className="mt-1 text-sm text-slate-700">This record is preserved for case history. Its proposed and reviewer-approved rulings are shown as recorded and cannot be changed here.</p>
        </section>
      )}
      <CaseDetails caseResult={caseResult} />

      {caseResult.judge && (
        <EscalationState escalation={caseResult.judge.escalation} />
      )}

      {caseResult.status === "pending_review" && (
        <section
          className="rounded-xl border border-amber-300 bg-amber-50 p-5"
          aria-label="Human Review Required"
          data-testid="pending-review"
        >
          <h2 className="text-lg font-bold text-amber-900">Human Review Required</h2>
          <p className="mt-2 text-sm text-amber-900">
            {caseResult.human_review_summary ??
              "This category is not yet supported for automated adjudication."}
          </p>
        </section>
      )}

      {/* Advocates on opposite sides */}
      {caseResult.advocates && (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AdvocatePanel
          role="rider"
          advocate={caseResult.advocates.rider}
          caseId={caseResult.case_id}
          syntheticReasoning={caseResult.synthetic_reasoning}
          side="left"
        />
        <AdvocatePanel
          role="driver"
          advocate={caseResult.advocates.driver}
          caseId={caseResult.case_id}
          syntheticReasoning={caseResult.synthetic_reasoning}
          side="right"
        />
      </div>
      )}

      {/* Judge ruling */}
      {caseResult.judge && <JudgeRuling judge={caseResult.judge} caseResult={caseResult} />}

      {caseResult.judge && (
        <ReviewerActions caseResult={caseResult} onUpdated={setCaseResult} />
      )}

      {(caseResult.evidence_audit || caseResult.fraud_assessment) && (
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2" aria-label="Model Reviews">
          {caseResult.evidence_audit && (
            <section className="rounded-xl border border-gray-200 bg-white p-5" aria-label="Evidence Audit" data-testid="evidence-audit">
              <header className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-bold text-gray-900">Evidence Audit</h2>
                <span className="text-xs text-gray-500">Provider: {caseResult.evidence_audit.provider.display_name ?? "Unknown provider"}</span>
              </header>
              {caseResult.evidence_audit.findings.length === 0 ? (
                <p className="mt-3 text-sm text-gray-600">No material claim concerns were identified.</p>
              ) : (
                <ul className="mt-3 flex flex-col gap-4">
                  {caseResult.evidence_audit.findings.map((finding, index) => (
                    <li key={`${finding.party}-${index}`} className="border-l-2 border-amber-400 pl-3">
                      <p className="text-xs font-semibold uppercase text-gray-500">{finding.party} · {finding.classification.replaceAll("_", " ")} · <span title={formatConfidenceA11y(finding.confidence)}>{formatConfidence(finding.confidence)} confidence</span></p>
                      <p className="mt-1 text-sm font-medium text-gray-900">{finding.claim_text}</p>
                      <p className="mt-1 text-sm text-gray-700">{finding.explanation}</p>
                      {finding.evidence_references.length > 0 && (
                        <div className="mt-2 flex flex-col gap-2">
                          {finding.evidence_references.map((evidenceId) => <EvidenceControl key={evidenceId} evidenceId={evidenceId} caseId={caseResult.case_id} />)}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {caseResult.fraud_assessment && (
            <section className="rounded-xl border border-gray-200 bg-white p-5" aria-label="Fraud Assessment" data-testid="fraud-assessment">
              <header className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-bold text-gray-900">Fraud Risk Assessment</h2>
                <span className="text-xs text-gray-500">Provider: {caseResult.fraud_assessment.provider.display_name ?? "Unknown provider"}</span>
              </header>
              <p className="mt-2 text-sm text-gray-800">
                Risk score: <span title={`Risk score: ${caseResult.fraud_assessment.risk_score.toFixed(3)} (displayed as ${formatConfidence(caseResult.fraud_assessment.risk_score)})`}>{formatConfidence(caseResult.fraud_assessment.risk_score)}</span>
                {" · "}confidence <span title={formatConfidenceA11y(caseResult.fraud_assessment.confidence)}>{formatConfidence(caseResult.fraud_assessment.confidence)}</span>
              </p>
              <p className="mt-1 text-xs text-gray-500">Risk informs the Judge’s assessment and does not automatically escalate a case.</p>
              {caseResult.fraud_assessment.findings.length > 0 && (
                <ul className="mt-3 flex flex-col gap-3">
                  {caseResult.fraud_assessment.findings.map((finding, index) => (
                    <li key={`${finding.finding_type}-${index}`} className="border-l-2 border-purple-300 pl-3">
                      <p className="text-xs font-semibold uppercase text-gray-500">{finding.party} · {finding.finding_type.replaceAll("_", " ")}</p>
                      <p className="mt-1 text-sm text-gray-800">{finding.summary}</p>
                      {finding.evidence_ids.length > 0 && (
                        <div className="mt-2 flex flex-col gap-2">
                          {finding.evidence_ids.map((evidenceId) => <EvidenceControl key={evidenceId} evidenceId={evidenceId} caseId={caseResult.case_id} />)}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </section>
      )}

      {/* External findings */}
      {caseResult.external_findings.length > 0 && (
        <section
          className="rounded-xl border border-gray-200 bg-white p-5"
          aria-label="External Findings"
          data-testid="external-findings"
        >
          <h2 className="text-lg font-bold text-gray-900 mb-3">External Findings</h2>
          <ul className="flex flex-col gap-3">
            {caseResult.external_findings.map((finding, i) => (
              <li key={i} className="text-sm border-l-2 border-gray-300 pl-3">
                <p className="text-gray-900">{finding.summary}</p>
                <p className="text-xs text-gray-500 mt-1">
                  <a
                    href={finding.source_url}
                    className="text-blue-600 hover:underline"
                    rel="noopener noreferrer"
                  >
                    {finding.source_url}
                  </a>
                  {" · "}
                  Reliability: {finding.reliability}
                  {" · "}
                  Evaluation: {finding.evaluation}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {caseResult.external_unavailable && caseResult.external_findings.length === 0 && (
        <p className="text-sm text-gray-500 italic">
          External provider was unavailable. The ruling proceeded on native evidence.
        </p>
      )}
    </div>
  );
}
