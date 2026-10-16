import type { Escalation } from "@/lib/api/types";
import { labelForEscalationReason } from "@/lib/api/format";

/**
 * Escalation state panel.
 *
 * When judge.escalation.escalated is true, renders the escalation reasons
 * and the human-review summary (RP-ESC-005).
 *
 * CRITICAL: the escalated flag is the ONLY thing the UI may branch on.
 * Never derive escalation by comparing confidence to a threshold.
 * 0.6996 rounds to 70.0% but does not clear the 0.70 bar.
 */
export function EscalationState({ escalation }: { escalation: Escalation }) {
  if (!escalation.escalated) {
    return (
      <div
        className="flex items-center gap-2 rounded-lg bg-green-50 border border-green-200 px-4 py-3"
        data-testid="escalation-state"
      >
        <svg className="w-5 h-5 text-green-600" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.094l4-5.5z"
            clipRule="evenodd"
          />
        </svg>
        <p className="text-sm text-green-800 font-medium">No escalation — case resolved automatically.</p>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col gap-4 rounded-xl border-2 border-tribunal-escalation/40 bg-red-50 p-5"
      data-testid="escalation-state"
      role="alert"
    >
      <header className="flex items-center gap-2">
        <svg className="w-6 h-6 text-tribunal-escalation" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
            clipRule="evenodd"
          />
        </svg>
        <h2 className="text-lg font-bold text-tribunal-escalation">Human decision needed</h2>
      </header>

      {/* Reasons */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Reasons</h3>
        <ul className="flex flex-col gap-1">
          {escalation.reasons.map((reason, i) => (
            <li key={i} className="text-sm text-gray-900 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-tribunal-escalation" aria-hidden="true" />
              {labelForEscalationReason(reason)}
            </li>
          ))}
        </ul>
      </div>

      {/* Human review summary */}
      {escalation.human_review_summary && (
        <details className="text-sm text-gray-900">
          <summary className="cursor-pointer font-medium">Full review notes</summary>
          <p className="mt-2 leading-relaxed whitespace-pre-wrap">{escalation.human_review_summary}</p>
        </details>
      )}
    </div>
  );
}
