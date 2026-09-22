"use client";

import { useState, useEffect, useCallback } from "react";
import type { CaseResult } from "@/lib/api/types";
import { getActiveClient } from "@/lib/api/fixture-client";
import { ApiError } from "@/lib/api/client";
import { CaseDetails } from "./case-details";
import { AdvocatePanel } from "./advocate-panel";
import { JudgeRuling } from "./judge-ruling";
import { EscalationState } from "./escalation-state";
import { LoadingState, EmptyState, ErrorState } from "./state-surfaces";

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
      <CaseDetails caseResult={caseResult} />

      {/* Escalation state — rendered prominently, before advocates and judge */}
      <EscalationState escalation={caseResult.judge.escalation} />

      {/* Advocates on opposite sides */}
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

      {/* Judge ruling */}
      <JudgeRuling judge={caseResult.judge} caseResult={caseResult} />

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
