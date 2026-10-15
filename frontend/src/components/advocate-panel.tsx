import { PolicyReference } from "./policy-reference";
import type { AdvocateOutput } from "@/lib/api/types";
import { SyntheticBadge } from "./synthetic-badge";
import { EvidenceControl } from "./evidence-control";

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
  policyVersion,
}: {
  role: "rider" | "driver";
  advocate: AdvocateOutput;
  caseId: string;
  syntheticReasoning: boolean;
  side: "left" | "right";
  policyVersion?: string;
}) {
  const isRider = role === "rider";
  const label = isRider ? "Rider Advocate" : "Driver Advocate";
  const accentColor = isRider ? "tribunal-rider" : "tribunal-driver";
  const providerIsMock = advocate.provider.kind === "deterministic-mock";
  const showBadge = syntheticReasoning || providerIsMock;

  return (
    <section
      className={`flex flex-col gap-4 rounded-xl border-2 ${isRider ? "border-blue-200" : "border-teal-200"} bg-white p-5 ${
        side === "left" ? "lg:mr-2" : "lg:ml-2"
      }`}
      aria-label={label}
      data-testid={`advocate-panel-${role}`}
    >
      <header className="flex items-center justify-between gap-2">
        <h2 className={`text-lg font-bold ${isRider ? "text-blue-800" : "text-teal-800"}`}>
          {label}
        </h2>
        <div className="flex items-center gap-2">
          {showBadge && <SyntheticBadge show={true} size="sm" />}
          {advocate.provider.kind === "rules-engine" && <span className="rounded-full bg-teal-50 px-2 py-1 text-xs font-medium text-teal-800">Rules-based review</span>}
        </div>
      </header>

      {/* Argument */}
      <div>
        <h3 className="mb-1 text-sm font-semibold text-gray-700">{isRider ? "Rider’s position" : "Driver’s position"}</h3>
        <p className="text-sm text-gray-900 leading-relaxed">{advocate.argument}</p>
      </div>

      {/* Claims with citations */}
      {advocate.claims.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">What the evidence shows</h3>
          <ol className="flex flex-col gap-3">
            {advocate.claims.map((claim, i) => (
              <li key={i} className="claim-card">
                <p className="text-sm leading-relaxed text-gray-900">{claim.text}</p>
                {claim.citations.length > 0 && <div className="claim-evidence-list" aria-label={`Evidence for claim ${i + 1}`}>
                  {claim.citations.map((citation) => <div key={`${citation.evidence_id}-${citation.field_path}`} className="citation-evidence">
                    <EvidenceControl
                      evidenceId={citation.evidence_id}
                      caseId={caseId}
                      title={labelForField(citation.field_path)}
                      summary={formatCitedFact(citation.field_path, citation.observed_value)}
                      citedField={citation.field_path}
                      observedValue={citation.observed_value}
                    />
                    <span className={`citation-state ${citation.valid ? "valid" : "invalid"}`}>
                      {citation.valid ? "Source checked" : "Citation needs review"}
                    </span>
                  </div>)}
                </div>}
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
              <PolicyReference key={ref} ruleId={ref} version={policyVersion} />
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
              <li key={i} className="rejected-evidence-item">
                <p>{rej.reason}</p>
                <EvidenceControl evidenceId={rej.evidence_id} caseId={caseId} title="Evidence not relied on" summary={rej.reason} />
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

      <details className="agent-technical-details">
        <summary>Agent details</summary>
        <dl><div><dt>Reasoning provider</dt><dd>{advocate.provider.display_name ?? (providerIsMock ? "Local deterministic" : "Not supplied")}</dd></div>
          <div><dt>Evidence IDs</dt><dd>{collectEvidenceIds(advocate).join(", ") || "None"}</dd></div>
          <div><dt>Invalid citations</dt><dd>{advocate.invalid_citation_count}</dd></div></dl>
      </details>
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

function labelForField(path: string): string {
  const key = path.split(".").at(-1) ?? path;
  const labels: Record<string, string> = {
    actual_distance_km: "Recorded route", planned_distance_km: "Planned route",
    min_distance_to_pickup_m: "Distance from pickup", driver_waited_seconds: "Waiting time",
    contact_attempt_recorded: "Contact attempt", quoted_fare_cents: "Quoted fare",
    charged_fare_cents: "Charged fare", cancellation_fee_cents: "Cancellation fee",
    waiting_fare_cents: "Waiting fee", latitude: "GPS location", longitude: "GPS location",
    accuracy_m: "GPS accuracy", deviation_pct: "Route distance difference",
  };
  return labels[key] ?? key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatCitedFact(path: string, value: unknown): string {
  const key = path.split(".").at(-1) ?? path;
  if (value === null || value === undefined) return "Value not available";
  if (key.endsWith("_cents")) return new Intl.NumberFormat("en-SG", { style: "currency", currency: "SGD" }).format(Number(value) / 100);
  if (key.endsWith("_km")) return `${value} km`;
  if (key.endsWith("_m")) return `${value} m`;
  if (key === "deviation_pct") return `${value}%`;
  if (key === "driver_waited_seconds") return `${Math.round(Number(value) / 60)} min`;
  if (key === "surge_multiplier") return `${value}×`;
  if (typeof value === "boolean") return value ? "Recorded" : "Not recorded";
  if (key === "latitude" || key === "longitude") return "Pin on map";
  return String(value);
}
