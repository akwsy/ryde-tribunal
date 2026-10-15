import type { CaseResult } from "@/lib/api/types";
import {
  labelForCategory,
  labelForCaseStatus,
  labelForRulingType,
  formatDateTime,
} from "@/lib/api/format";
import { SyntheticBadge } from "./synthetic-badge";

/** A short, reviewer-first case summary. Internal fields stay out of the reading path. */
export function CaseDetails({ caseResult }: { caseResult: CaseResult }) {
  const facts = caseResult.case_facts && typeof caseResult.case_facts === "object"
    ? caseResult.case_facts as Record<string, unknown>
    : {};
  const subject = textFact(facts.subject);
  const description = textFact(facts.description);
  const filedBy = textFact(facts.filed_by);
  const pickup = textFact(facts.pickup);
  const dropoff = textFact(facts.dropoff);

  return (
    <section className="flex flex-col gap-4 rounded-xl border border-gray-200 bg-white p-5" aria-label="Case Details" data-testid="case-details">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="text-sm font-medium text-teal-800">{labelForCategory(caseResult.category)}</p>
          <h1 className="mt-1 text-2xl font-bold text-gray-900">
            {subject ?? labelForCategory(caseResult.category)}
          </h1>
          <p className="mt-1 text-sm text-gray-500" data-testid="case-id">
            Case {caseResult.case_id} <span aria-hidden="true">·</span> Trip {caseResult.ride_id}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`inline-block rounded-full px-3 py-1 text-sm font-medium ${statusColor(caseResult.status)}`} data-testid="case-status">
            {labelForCaseStatus(caseResult.status)}
          </span>
          <SyntheticBadge show={caseResult.synthetic_reasoning} size="md" />
        </div>
      </header>

      {(pickup || dropoff) && <p className="text-sm text-slate-700">{pickup ?? "Pickup not recorded"}<span className="mx-2 text-slate-400" aria-label="to">→</span>{dropoff ?? "Destination not recorded"}</p>}
      {description && <p className="max-w-4xl text-sm leading-relaxed text-slate-700">{description}</p>}

      {(() => {
        const finalRuling = caseResult.reviewer_approved_ruling;
        const modelRuling = caseResult.model_proposed_ruling;
        const ruling = finalRuling ?? caseResult.judge ?? modelRuling;
        if (!ruling) return null;
        const approved = Boolean(finalRuling);
        const awaitingReview = caseResult.status === "pending_review" || caseResult.status === "escalated";
        return <section className={`case-outcome-card${awaitingReview ? " needs-review" : approved ? " approved" : " proposed"}`} aria-label="Case outcome">
          <div className="case-outcome-heading"><span>{awaitingReview ? "Needs a reviewer" : approved ? "Reviewer decision" : caseResult.case_source === "archive" ? "Recorded decision" : "Suggested outcome"}</span>
            <span className="case-outcome-status">{labelForCaseStatus(caseResult.status)}</span></div>
          <h2>{labelForRulingType(ruling.ruling_type)}</h2>
          <p>{ruling.recommended_action.description}</p>
          {ruling.recommended_action.amount && <p className="case-outcome-amount">{new Intl.NumberFormat("en-SG", { style: "currency", currency: ruling.recommended_action.amount.currency }).format(ruling.recommended_action.amount.amount_cents / 100)}</p>}
          {ruling.recommended_action.delivery === "voucher" && <p className="case-outcome-delivery">Voucher recommendation · no payment has been issued</p>}
          {finalRuling?.rationale && <p className="case-outcome-rationale">Reviewer’s reason: {finalRuling.rationale}</p>}
        </section>;
      })()}

      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-gray-500">
        <span>Filed {formatDateTime(caseResult.created_at)}</span>
        {filedBy && <span>Filed by {filedBy}</span>}
        <span data-testid="urgency-display">Priority {Math.round(caseResult.urgency * 100)}%</span>
      </div>

      {(caseResult.model_proposed_ruling || caseResult.reviewer_approved_ruling) && (
        <details className="agent-technical-details" aria-label="Recorded rulings">
          <summary>Compare model suggestion and reviewer decision</summary>
          <section className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            {caseResult.model_proposed_ruling && <RulingCard testId="model-proposed-ruling" title="Model suggestion" ruling={caseResult.model_proposed_ruling} />}
            {caseResult.reviewer_approved_ruling && <RulingCard testId="reviewer-approved-ruling" title="Reviewer decision" ruling={caseResult.reviewer_approved_ruling} />}
          </section>
        </details>
      )}

      <details className="agent-technical-details">
        <summary>Case record details</summary>
        <dl className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          <div><dt className="text-gray-500">Case reference</dt><dd>{caseResult.case_id}</dd></div>
          <div><dt className="text-gray-500">Trip reference</dt><dd>{caseResult.ride_id}</dd></div>
          <div><dt className="text-gray-500">Policy version</dt><dd>{caseResult.policy_version}</dd></div>
          <div><dt className="text-gray-500">Other checks</dt><dd>{caseResult.external_findings.length ? `${caseResult.external_findings.length} additional finding${caseResult.external_findings.length === 1 ? "" : "s"}` : caseResult.external_unavailable ? "External checks unavailable" : "No additional findings"}</dd></div>
        </dl>
      </details>
    </section>
  );
}

function RulingCard({ title, ruling, testId }: { title: string; ruling: NonNullable<CaseResult["model_proposed_ruling"]>; testId: string }) {
  return <div data-testid={testId} className="rounded-lg border border-gray-200 bg-gray-50 p-4">
    <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
    <p className="mt-1 font-medium text-gray-900">{labelForRulingType(ruling.ruling_type)}</p>
    <p className="text-sm text-gray-700">{ruling.recommended_action.description}</p>
    <p className="mt-1 text-xs text-gray-500">{ruling.credibility.replaceAll("_", " ")}</p>
  </div>;
}

function textFact(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function statusColor(status: CaseResult["status"]): string {
  if (status === "processing") return "bg-teal-100 text-teal-900";
  if (status === "escalated" || status === "pending_review") return "bg-amber-100 text-amber-900";
  if (status === "resolved") return "bg-green-100 text-green-800";
  if (status === "overridden") return "bg-purple-100 text-purple-800";
  return "bg-gray-100 text-gray-800";
}
