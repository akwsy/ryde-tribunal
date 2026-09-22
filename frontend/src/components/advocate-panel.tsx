import type { AdvocateOutput } from "@/lib/api/types";
import { SyntheticBadge } from "./synthetic-badge";
import { EvidenceControl } from "./evidence-control";
import { VerificationBadge } from "./evidence-control";

/**
 * Advocate panel — renders the Rider or Driver advocate's argument, claims with
 * citations, policy references, rejected evidence, invalid citation count,
 * and provider info. Renders the synthetic badge when the provider is
 * deterministic-mock or when the case-level synthetic_reasoning flag is true.
 *
 * Rider and Driver panels are placed on opposite sides (left / right) via
 * the `side` prop.
 */
export function AdvocatePanel({
  role,
  advocate,
  caseId,
  syntheticReasoning,
  side,
}: {
  role: "rider" | "driver";
  advocate: AdvocateOutput;
  caseId: string;
  syntheticReasoning: boolean;
  side: "left" | "right";
}) {
  const isRider = role === "rider";
  const label = isRider ? "Rider Advocate" : "Driver Advocate";
  const accentColor = isRider ? "tribunal-rider" : "tribunal-driver";
  const providerIsMock = advocate.provider.kind === "deterministic-mock";
  const showBadge = syntheticReasoning || providerIsMock;

  return (
    <section
      className={`flex flex-col gap-4 rounded-xl border-2 border-${accentColor}/30 bg-white p-5 ${
        side === "left" ? "lg:mr-2" : "lg:ml-2"
      }`}
      aria-label={label}
      data-testid={`advocate-panel-${role}`}
    >
      <header className="flex items-center justify-between gap-2">
        <h2 className={`text-lg font-bold text-${accentColor}`}>
          {label}
        </h2>
        <div className="flex items-center gap-2">
          {showBadge && <SyntheticBadge show={true} size="sm" />}
        </div>
      </header>

      {/* Provider info */}
      <p className="text-xs text-gray-500">
        Provider: <span className="font-mono">{advocate.provider.kind}</span>
        {advocate.provider.model && (
          <> · Model: <span className="font-mono">{advocate.provider.model}</span></>
        )}
      </p>

      {/* Argument */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-1">Argument</h3>
        <p className="text-sm text-gray-900 leading-relaxed">{advocate.argument}</p>
      </div>

      {/* Claims with citations */}
      {advocate.claims.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Claims</h3>
          <ol className="flex flex-col gap-3 list-decimal list-inside">
            {advocate.claims.map((claim, i) => (
              <li key={i} className="text-sm text-gray-900">
                <p className="leading-relaxed">{claim.text}</p>
                {claim.citations.length > 0 && (
                  <ul className="mt-1 ml-4 flex flex-col gap-1 list-disc list-inside">
                    {claim.citations.map((citation, j) => (
                      <li key={j} className="text-xs text-gray-600">
                        <span className="font-mono">{citation.evidence_id}</span>
                        {" → "}
                        <span className="font-mono">{citation.field_path}</span>
                        {" = "}
                        <span className="font-mono">{String(citation.observed_value)}</span>
                        {!citation.valid && (
                          <span className="ml-1 text-red-600 font-medium">(invalid)</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Policy references */}
      {advocate.policy_references.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-1">Policy References</h3>
          <div className="flex flex-wrap gap-1.5">
            {advocate.policy_references.map((ref) => (
              <span
                key={ref}
                className="inline-block rounded bg-blue-50 border border-blue-200 px-2 py-0.5 text-xs font-mono text-blue-800"
              >
                {ref}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Rejected evidence */}
      {advocate.rejected_evidence && advocate.rejected_evidence.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-1">Rejected Evidence</h3>
          <ul className="flex flex-col gap-1">
            {advocate.rejected_evidence.map((rej, i) => (
              <li key={i} className="text-xs text-gray-600">
                <span className="font-mono">{rej.evidence_id}</span>
                {": "}
                {rej.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Invalid citation count */}
      {advocate.invalid_citation_count > 0 && (
        <p className="text-xs text-red-600">
          <span className="font-semibold">Invalid citations:</span> {advocate.invalid_citation_count}
        </p>
      )}

      {/* Evidence controls */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Evidence</h3>
        <div className="flex flex-col gap-2">
          {collectEvidenceIds(advocate).map((eid) => (
            <EvidenceControl key={eid} evidenceId={eid} caseId={caseId} />
          ))}
        </div>
      </div>
    </section>
  );
}

/** Collect all evidence IDs referenced in an advocate's claims and rejected_evidence. */
function collectEvidenceIds(advocate: AdvocateOutput): string[] {
  const ids = new Set<string>();
  for (const claim of advocate.claims) {
    for (const citation of claim.citations) {
      ids.add(citation.evidence_id);
    }
  }
  if (advocate.rejected_evidence) {
    for (const rej of advocate.rejected_evidence) {
      ids.add(rej.evidence_id);
    }
  }
  return [...ids];
}
