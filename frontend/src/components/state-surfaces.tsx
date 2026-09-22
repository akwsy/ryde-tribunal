/**
 * First-class state surfaces: loading, empty, error, escalated.
 *
 * These are NOT afterthoughts. Each is a distinct, correct surface.
 * - Loading: skeleton with aria-busy.
 * - Empty: "case not found" with the case ID.
 * - Error: distinguishes internal_error (500) from database_unavailable.
 * - Escalated is handled by the EscalationState component, but this
 *   ErrorState is for HTTP-level errors.
 */

export function LoadingState({ caseId }: { caseId?: string }) {
  return (
    <div
      className="flex flex-col gap-4 p-8"
      aria-busy="true"
      aria-label="Loading case"
      data-testid="loading-state"
    >
      <div className="h-8 w-48 animate-pulse rounded-lg bg-gray-200" />
      <div className="h-4 w-full animate-pulse rounded bg-gray-200" />
      <div className="h-4 w-3/4 animate-pulse rounded bg-gray-200" />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
        <div className="h-64 animate-pulse rounded-xl bg-gray-200" />
        <div className="h-64 animate-pulse rounded-xl bg-gray-200" />
        <div className="h-64 animate-pulse rounded-xl bg-gray-200" />
      </div>
      <p className="text-sm text-gray-500">
        Loading case{caseId ? ` ${caseId}` : ""}…
      </p>
    </div>
  );
}

export function EmptyState({ caseId }: { caseId: string }) {
  return (
    <div
      className="flex flex-col items-center gap-4 p-12 text-center"
      data-testid="empty-state"
    >
      <svg className="w-16 h-16 text-gray-300" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path d="M9 2a1 1 0 00-1 1v1H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V6a2 2 0 00-2-2h-2V3a1 1 0 00-1-1H9z" />
      </svg>
      <h2 className="text-xl font-bold text-gray-900">Case Not Found</h2>
      <p className="text-sm text-gray-600">
        Case <span className="font-mono">{caseId}</span> does not exist or has been removed.
      </p>
    </div>
  );
}

export function ErrorState({
  caseId,
  code,
  message,
  status,
}: {
  caseId?: string;
  code: string;
  message: string;
  status: number;
}) {
  const isDatabaseUnavailable = code === "database_unavailable";
  const isInternal = code === "internal_error" || status >= 500;

  return (
    <div
      className="flex flex-col items-center gap-4 p-12 text-center rounded-xl border-2 border-red-200 bg-red-50"
      role="alert"
      data-testid="error-state"
      data-error-code={code}
      data-error-status={status}
    >
      <svg className="w-16 h-16 text-red-400" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8  8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
          clipRule="evenodd"
        />
      </svg>
      <h2 className="text-xl font-bold text-red-900">
        {isDatabaseUnavailable
          ? "Database Unavailable"
          : isInternal
            ? "Internal Error"
            : "Error"}
      </h2>
      <p className="text-sm text-red-700 max-w-md">
        {message}
      </p>
      <p className="text-xs text-red-500">
        Error code: <span className="font-mono">{code}</span>
        {caseId && (
          <>
            {" · Case: "}
            <span className="font-mono">{caseId}</span>
          </>
        )}
        {" · HTTP "}
        <span className="font-mono">{status}</span>
      </p>
      {isDatabaseUnavailable && (
        <p className="text-xs text-red-600 italic">
          A failure never returns a ruling. No case data can be displayed.
        </p>
      )}
    </div>
  );
}
