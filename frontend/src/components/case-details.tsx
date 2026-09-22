import type { CaseResult } from "@/lib/api/types";
import {
  labelForCategory,
  labelForCaseStatus,
  formatDateTime,
} from "@/lib/api/format";
import { SyntheticBadge } from "./synthetic-badge";

/**
 * Case details header — case_id, ride_id, category, status, timestamps,
 * policy_version, urgency. Shows the synthetic-reasoning badge at the
 * case level when synthetic_reasoning is true.
 */
export function CaseDetails({ caseResult }: { caseResult: CaseResult }) {
  return (
    <section
      className="flex flex-col gap-4 rounded-xl border border-gray-200 bg-white p-5"
      aria-label="Case Details"
      data-testid="case-details"
    >
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900" data-testid="case-id">
            {caseResult.case_id}
          </h1>
          <p className="text-sm text-gray-500">
            Ride: <span className="font-mono">{caseResult.ride_id}</span>
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <span
            className={`inline-block rounded-full px-3 py-1 text-sm font-medium ${
              caseResult.status === "escalated"
                ? "bg-red-100 text-red-800"
                : caseResult.status === "resolved"
                  ? "bg-green-100 text-green-800"
                  : caseResult.status === "pending_review"
                    ? "bg-yellow-100 text-yellow-800"
                    : caseResult.status === "overridden"
                      ? "bg-purple-100 text-purple-800"
                      : "bg-gray-100 text-gray-800"
            }`}
            data-testid="case-status"
          >
            {labelForCaseStatus(caseResult.status)}
          </span>
          <span className="inline-block rounded-full bg-blue-50 border border-blue-200 px-3 py-1 text-sm font-medium text-blue-800">
            {labelForCategory(caseResult.category)}
          </span>
          <SyntheticBadge show={caseResult.synthetic_reasoning} size="md" />
        </div>
      </header>

      <dl className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-2 text-sm">
        <div>
          <dt className="text-xs text-gray-500">Filed</dt>
          <dd className="text-gray-900">{formatDateTime(caseResult.created_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500">Policy Version</dt>
          <dd className="font-mono text-gray-900">{caseResult.policy_version}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500">Urgency</dt>
          <dd className="text-gray-900" data-testid="urgency-display">
            {(caseResult.urgency * 100).toFixed(0)}%
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500">External Findings</dt>
          <dd className="text-gray-900">
            {caseResult.external_findings.length > 0
              ? `${caseResult.external_findings.length} item(s)`
              : caseResult.external_unavailable
                ? "Provider unavailable"
                : "None"}
          </dd>
        </div>
      </dl>

      {/* Case facts */}
      {caseResult.case_facts && Object.keys(caseResult.case_facts).length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-sm font-medium text-blue-600 hover:text-blue-800">
            Case Facts
          </summary>
          <pre className="mt-2 text-xs bg-gray-50 border border-gray-200 rounded p-3 overflow-x-auto">
            {JSON.stringify(caseResult.case_facts, (k, v) => typeof v === "boolean" ? (v ? "Yes" : "No") : v, 2)}
          </pre>
        </details>
      )}
    </section>
  );
}
