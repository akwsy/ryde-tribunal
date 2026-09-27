"use client";

import { useState, useCallback, useId } from "react";
import type { Evidence } from "@/lib/api/types";
import {
  labelForEvidenceClass,
  labelForVerificationStatus,
  formatDateTime,
} from "@/lib/api/format";
import { getActiveClient } from "@/lib/api/fixture-client";
import { ApiError } from "@/lib/api/client";

/**
 * Clickable evidence control that reveals the underlying evidence record.
 *
 * Fetches GET /api/v1/evidence/{evidence_id} on demand (lazy).
 * Renders verification status and uncertainty percentage.
 * Handles the case where uncertainty_pct is absent (null).
 *
 * Keyboard accessible: the disclosure button is a native <button>,
 * focusable, and operable with Enter and Space.
 */
export function EvidenceControl({
  evidenceId,
  caseId,
}: {
  evidenceId: string;
  caseId: string;
}) {
  const detailId = `evidence-detail-${useId().replaceAll(":", "")}`;
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const handleToggle = useCallback(async () => {
    if (!expanded && !evidence) {
      setLoading(true);
      setError(null);
      try {
        const client = getActiveClient();
        const result = await client.getEvidence(evidenceId);
        setEvidence(result);
        setExpanded(true);
      } catch (e) {
        if (e instanceof ApiError) {
          setError(e.message);
        } else {
          setError("Failed to load evidence.");
        }
      } finally {
        setLoading(false);
      }
    } else {
      setExpanded(!expanded);
    }
  }, [expanded, evidence, evidenceId]);

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden" data-testid={`evidence-control-${evidenceId}`}>
      <button
        type="button"
        onClick={handleToggle}
        disabled={loading}
        aria-expanded={expanded}
        aria-controls={detailId}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-inset disabled:opacity-50"
      >
        <span className="flex items-center gap-2">
          <svg
            className={`w-4 h-4 transition-transform ${expanded ? "rotate-90" : ""}`}
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
              clipRule="evenodd"
            />
          </svg>
          <span className="font-mono text-sm font-medium text-gray-900">{evidenceId}</span>
        </span>
        {loading && (
          <span className="text-sm text-gray-500" aria-label="Loading evidence">
            Loading…
          </span>
        )}
      </button>

      {expanded && evidence && (
        <div
          id={detailId}
          className="border-t border-gray-200 px-4 py-3 bg-gray-50"
          data-testid={`evidence-detail-${evidenceId}`}
        >
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="font-medium text-gray-600">Evidence ID</dt>
            <dd className="font-mono text-gray-900">{evidence.evidence_id}</dd>

            <dt className="font-medium text-gray-600">Case ID</dt>
            <dd className="font-mono text-gray-900">{evidence.case_id}</dd>

            <dt className="font-medium text-gray-600">Class</dt>
            <dd className="text-gray-900">{labelForEvidenceClass(evidence.class)}</dd>

            <dt className="font-medium text-gray-600">Source</dt>
            <dd className="text-gray-900">{evidence.source.replace(/_/g, " ")}</dd>

            <dt className="font-medium text-gray-600">Recorded At</dt>
            <dd className="text-gray-900">{formatDateTime(evidence.recorded_at)}</dd>

            <dt className="font-medium text-gray-600">Visibility</dt>
            <dd className="text-gray-900">{evidence.visibility.replace(/_/g, " ")}</dd>

            <dt className="font-medium text-gray-600">Verification</dt>
            <dd>
              <VerificationBadge
                status={evidence.verification.status}
                uncertaintyPct={evidence.verification.uncertainty_pct}
              />
            </dd>
          </dl>

          {evidence.provenance && Object.keys(evidence.provenance).length > 0 && (
            <div className="mt-3">
              <p className="text-sm font-medium text-gray-600 mb-1">Provenance</p>
              <pre className="text-xs bg-white border border-gray-200 rounded p-2 overflow-x-auto">
                {JSON.stringify(evidence.provenance, null, 2)}
              </pre>
            </div>
          )}

          {evidence.payload && Object.keys(evidence.payload).length > 0 && (
            <div className="mt-3">
              <p className="text-sm font-medium text-gray-600 mb-1">Payload</p>
              <pre className="text-xs bg-white border border-gray-200 rounded p-2 overflow-x-auto max-h-64">
                {JSON.stringify(evidence.payload, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {expanded && error && (
        <div
          id={detailId}
          className="border-t border-gray-200 px-4 py-3 bg-red-50"
          role="alert"
        >
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}
    </div>
  );
}

/**
 * Verification status badge with uncertainty percentage.
 * Handles the case where uncertainty_pct is absent (null).
 */
export function VerificationBadge({
  status,
  uncertaintyPct,
  size = "md",
}: {
  status: string;
  uncertaintyPct?: number | null;
  size?: "sm" | "md";
}) {
  const colorClass =
    status === "verified"
      ? "bg-green-100 text-green-800 border-green-300"
      : status === "unverified"
        ? "bg-yellow-100 text-yellow-800 border-yellow-300"
        : status === "disputed"
          ? "bg-orange-100 text-orange-800 border-orange-300"
          : status === "unverifiable"
            ? "bg-gray-200 text-gray-700 border-gray-400"
            : "bg-gray-100 text-gray-800 border-gray-300";

  const sizeClass = size === "sm" ? "text-xs px-1.5 py-0.5" : "text-sm px-2 py-1";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border ${colorClass} ${sizeClass}`}
      data-testid="verification-badge"
    >
      <span>{labelForVerificationStatus(status)}</span>
      {uncertaintyPct != null ? (
        <span className="font-mono font-semibold" title="Uncertainty percentage">
          ±{uncertaintyPct}%
        </span>
      ) : (
        <span className="italic text-gray-500" title="Uncertainty not available">
          uncertainty N/A
        </span>
      )}
    </span>
  );
}
