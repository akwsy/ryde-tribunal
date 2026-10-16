"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { CaseResult, Evidence } from "@/lib/api/types";
import { getActiveClient } from "@/lib/api/fixture-client";
import { ApiError } from "@/lib/api/client";
import { AgentTimeline } from "./agent-timeline";
import { EvidenceReviewSummary } from "./evidence-review-summary";
import { CaseDetails } from "./case-details";
import { ReviewerActions } from "./reviewer-actions";
import { AdvocatePanel } from "./advocate-panel";
import { JudgeRuling } from "./judge-ruling";
import { EscalationState } from "./escalation-state";
import { EvidenceControl } from "./evidence-control";
import { LoadingState, EmptyState, ErrorState } from "./state-surfaces";
import { formatConfidence, formatConfidenceA11y } from "@/lib/api/format";
import { factValue, policyLabel } from "@/lib/review-copy";

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
  const [adjudicating, setAdjudicating] = useState(false);
  const [loading, setLoading] = useState(true);
  const autoStarted = useRef(false);
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

  // Deep links and refreshes receive the same automatic review as dashboard users.
  useEffect(() => {
    if (!caseResult || caseResult.status !== "queued" || caseResult.case_source !== "live" || autoStarted.current) return;
    autoStarted.current = true;
    setAdjudicating(true);
    void getActiveClient().adjudicateDispute(caseId, `case-view-auto-${caseId}`)
      .then(setCaseResult)
      .catch(async () => {
        // A dashboard tab may have won the atomic claim; reload its persisted status.
        try { setCaseResult(await getActiveClient().getDispute(caseId)); } catch { /* Keep the filed case visible. */ }
      })
      .finally(() => setAdjudicating(false));
  }, [caseId, caseResult]);

  // Keep a case opened during automatic processing current without flashing the full-page loader.
  useEffect(() => {
    if (!caseResult || caseResult.status !== "processing") return;
    const timer = window.setInterval(() => {
      void getActiveClient().getDispute(caseId).then(setCaseResult).catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [caseId, caseResult]);

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
      {caseResult.case_source === "archive" && archivedEvidence(caseResult).length > 0 && <section className="rounded-xl border border-slate-200 bg-white p-5" aria-label="Evidence recorded with this case">
        <h2 className="text-base font-semibold text-slate-900">Evidence recorded with this case</h2>
        <p className="mt-1 text-sm text-slate-600">Open any item to inspect its original record and verification details.</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">{archivedEvidence(caseResult).map((evidence) => <EvidenceControl key={evidence.evidence_id} evidenceId={evidence.evidence_id} caseId={caseResult.case_id} title={labelForArchivedEvidence(evidence.class)} initialEvidence={evidence} />)}</div>
      </section>}
      {caseResult.status === "queued" && <section className="outcome-summary"><h2>Ready for adjudication</h2><p className="text-sm text-slate-600">The agents will retrieve evidence, present both cases and apply the current policy.</p>
        <button type="button" disabled={adjudicating} className="mt-4 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={async () => {
          if (adjudicating) return;
          setAdjudicating(true);
          try { setCaseResult(await getActiveClient().adjudicateDispute(caseId,crypto.randomUUID())); }
          catch (cause) { setError({code:"internal_error",message:cause instanceof Error ? cause.message : "Adjudication failed",status:500}); }
          finally { setAdjudicating(false); }
        }}>{adjudicating ? "Agents are reviewing evidence…" : "Start adjudication"}</button>
        {adjudicating && <p role="status" className="mt-3 text-sm text-slate-600">Waiting for the recorded agent result. A provider failure may require human review.</p>}
      </section>}
      {caseResult.status === "processing" && <section className="flex items-center gap-3 rounded-xl border border-teal-200 bg-teal-50 p-4" role="status">
        <span aria-hidden="true" className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-teal-700 border-t-transparent" />
        <div><h2 className="font-semibold text-teal-950">Agents are reviewing this dispute</h2><p className="text-sm text-teal-900">The evidence checker will verify citations before the Judge makes a recommendation.</p></div>
      </section>}
      {caseResult.judge && <JudgeRuling judge={caseResult.judge} caseResult={caseResult} />}
      {caseResult.party_explanations && <details className="rounded-xl border border-slate-200 bg-white p-5"><summary className="cursor-pointer font-semibold">Party explanations</summary>
        <div className="mt-4 grid gap-5 md:grid-cols-2"><div><h3 className="font-semibold">For the rider</h3><p className="mt-2 text-sm">{caseResult.party_explanations.rider}</p></div><div><h3 className="font-semibold">For the driver</h3><p className="mt-2 text-sm">{caseResult.party_explanations.driver}</p></div></div>
        <button className="mt-4 rounded border px-3 py-2 text-sm" type="button" onClick={() => {
          const blob = new Blob([`Case ${caseResult.case_id}\n\nFor the rider\n${caseResult.party_explanations?.rider}\n\nFor the driver\n${caseResult.party_explanations?.driver}\n`],{type:"text/plain"});
          const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href=url; anchor.download=`${caseResult.case_id}-explanations.txt`; anchor.click(); URL.revokeObjectURL(url);
        }}>Export explanations</button>
      </details>}

      {caseResult.judge && (
        <EscalationState escalation={caseResult.judge.escalation} />
      )}

      {caseResult.status === "pending_review" && !caseResult.judge?.escalation.escalated && (
        <section
          className="rounded-xl border border-amber-300 bg-amber-50 p-5"
          aria-label="Human Review Required"
          data-testid="pending-review"
        >
          <h2 className="text-lg font-bold text-amber-900">Human Review Required</h2>
        <p className="mt-2 text-sm text-amber-900">Automated checks are complete. A reviewer must make the final decision.</p>
        {caseResult.human_review_summary && <details className="mt-2 text-sm text-amber-900"><summary className="cursor-pointer">Full review notes</summary><p className="mt-2 whitespace-pre-wrap">{caseResult.human_review_summary}</p></details>}
        </section>
      )}

      {caseResult.triage && <section className="rounded-xl border border-amber-200 bg-amber-50 p-5" aria-label="Automated evidence triage">
        <h2 className="text-lg font-bold text-amber-950">Automated checks completed</h2>
        <p className="mt-1 text-sm text-amber-900">A reviewer makes the final decision. The filer’s category details are claims until verified.</p>
        <p className="mt-2 text-sm text-amber-950">{caseResult.triage.verified_evidence_ids?.length ?? 0} verified record(s) · {caseResult.triage.unverified_evidence_ids?.length ?? 0} item(s) need verification</p>
        {(caseResult.triage.unverified_evidence_ids?.length ?? 0) > 0 && <div className="mt-3 grid gap-3 sm:grid-cols-2">{caseResult.triage.unverified_evidence_ids?.map((evidenceId) => <EvidenceControl key={evidenceId} evidenceId={evidenceId} caseId={caseResult.case_id} title="Submitted document" />)}</div>}
        {Object.keys(caseResult.triage.reported_category_details ?? {}).length > 0 && <dl className="mt-3 grid gap-x-5 gap-y-1 sm:grid-cols-2">{Object.entries(caseResult.triage.reported_category_details ?? {}).map(([key, value]) => <div key={key} className="text-sm"><dt className="inline font-medium">{categoryDetailLabel(key)}: </dt><dd className="inline">{categoryDetailValue(key, value)}</dd></div>)}</dl>}
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-amber-950">{caseResult.triage.next_steps.map((step, index) => <li key={`${index}-${step}`}>{step}</li>)}</ul>
        {caseResult.triage.policy_sources.length > 0 && <div className="mt-4 border-t border-amber-200 pt-3">
          <h3 className="text-sm font-semibold text-amber-950">Applicable guidance</h3>
          <ul className="mt-2 space-y-2 text-sm">{caseResult.triage.policy_sources.map((item) => <li key={item.rule_id}>
            <span className="font-medium">{policyLabel(item.rule_id)}: </span>{item.text}{item.source?.url && <a className="ml-1 font-medium text-teal-800 underline" href={item.source.url} target="_blank" rel="noreferrer">Ryde source</a>}
          </li>)}</ul>
        </div>}
      </section>}

      <EvidenceReviewSummary result={caseResult} />
      {/* Advocates on opposite sides */}
      {caseResult.advocates && (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AdvocatePanel
          policyVersion={caseResult.policy_version}
          role="rider"
          advocate={caseResult.advocates.rider}
          caseId={caseResult.case_id}
          syntheticReasoning={caseResult.synthetic_reasoning}
          side="left"
        />
        <AdvocatePanel
          policyVersion={caseResult.policy_version}
          role="driver"
          advocate={caseResult.advocates.driver}
          caseId={caseResult.case_id}
          syntheticReasoning={caseResult.synthetic_reasoning}
          side="right"
        />
      </div>
      )}

      <details className="rounded-xl border border-slate-200 bg-white p-5"><summary className="cursor-pointer font-semibold text-slate-800">Evidence checks and review history</summary><div className="mt-4 space-y-4"><AgentTimeline result={caseResult} /></div></details>

      {caseResult.judge && caseResult.case_source !== "archive" && (
        <ReviewerActions caseResult={caseResult} onUpdated={setCaseResult} />
      )}

      {caseResult.fraud_assessment && (
        <details className="agent-technical-details rounded-xl border border-slate-200 bg-white p-5" aria-label="Additional review checks">
          <summary>Additional review checks</summary>
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2" aria-label="Model Reviews">
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
        </details>
      )}

      {/* External findings */}
      {caseResult.external_findings.length > 0 && (
        <details className="agent-technical-details rounded-xl border border-slate-200 bg-white p-5">
          <summary>Additional information ({caseResult.external_findings.length})</summary>
        <section aria-label="External Findings" data-testid="external-findings">
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
        </details>
      )}

      {caseResult.external_unavailable && caseResult.external_findings.length === 0 && (
        <p className="text-sm text-gray-500 italic">
          External provider was unavailable. The ruling proceeded on native evidence.
        </p>
      )}
    </div>
  );
}

function archivedEvidence(result: CaseResult): Evidence[] {
  const rows = result.case_facts.archived_evidence;
  if (!Array.isArray(rows)) return [];
  const classes = new Set<Evidence["class"]>(["gps_telemetry", "chat_log", "app_event", "fare", "profile_history", "attachment", "external"]);
  const sources = new Set<Evidence["source"]>(["system_record", "company_imported", "rider_submitted", "driver_submitted", "external"]);
  const visibilities = new Set<Evidence["visibility"]>(["both", "rider_only", "driver_only", "reviewer_only"]);
  const statuses = new Set(["verified", "unverified", "disputed", "unverifiable"]);
  return rows.flatMap((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return [];
    const row = value as Record<string, unknown>;
    if (typeof row.evidence_id !== "string") return [];
    const verification = row.verification && typeof row.verification === "object" ? row.verification as Record<string, unknown> : {};
    const evidenceClass = typeof row.evidence_class === "string" && classes.has(row.evidence_class as Evidence["class"]) ? row.evidence_class as Evidence["class"] : "attachment";
    const source = typeof row.source === "string" && sources.has(row.source as Evidence["source"]) ? row.source as Evidence["source"] : "external";
    const visibility = typeof row.visibility === "string" && visibilities.has(row.visibility as Evidence["visibility"]) ? row.visibility as Evidence["visibility"] : "reviewer_only";
    const status = typeof verification.status === "string" && statuses.has(verification.status) ? verification.status as Evidence["verification"]["status"] : "unverified";
    return [{
      evidence_id: row.evidence_id,
      case_id: result.case_id,
      class: evidenceClass,
      source,
      recorded_at: typeof row.recorded_at === "string" ? row.recorded_at : result.created_at,
      provenance: row.provenance && typeof row.provenance === "object" ? row.provenance as Evidence["provenance"] : {},
      verification: { status, method: typeof verification.method === "string" ? verification.method : null, uncertainty_pct: typeof verification.uncertainty_pct === "number" ? verification.uncertainty_pct : null },
      visibility,
      payload: row.payload && typeof row.payload === "object" && !Array.isArray(row.payload) ? row.payload as Record<string, unknown> : {},
    }];
  });
}

function labelForArchivedEvidence(value: Evidence["class"]): string {
  return ({ gps_telemetry: "Trip locations", chat_log: "Trip messages", app_event: "Trip event", fare: "Fare record", profile_history: "Account history", attachment: "Case attachment", external: "External record" })[value];
}

function categoryDetailLabel(key: string): string {
  return ({ incident_timing: "When it happened", item_description: "Item", last_known_location: "Last known location",
    reported_item_status: "Reported item status", damage_description: "Damage or cleaning", claim_type: "Claim type",
    claim_amount_cents: "Amount claimed", fee_type: "Charge type", event_timing: "Disputed timing",
    disputed_component: "Fare item", incident_type: "Safety concern", conduct_type: "Conduct reported" } as Record<string, string>)[key]
    ?? key.replaceAll("_", " ");
}

function categoryDetailValue(key: string, value: unknown): string {
  return factValue(key, value);
}
