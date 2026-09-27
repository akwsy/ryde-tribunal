import type { CaseResult } from "@/lib/api/types";

/**
 * FIXTURE — not production data. All data is synthetic.
 *
 * Shape transcribed from docs/02-api-contract.md §3 (CaseResult) and
 * shared/openapi.yaml schemas. This is the "happy path" resolved case
 * with synthetic_reasoning: false.
 */
export const caseResultResolved: CaseResult = {
  case_id: "DSP-000045",
  case_source: "live",
  ride_id: "RIDE-000123",
  category: "route_deviation",
  status: "resolved",
  synthetic: true,
  synthetic_reasoning: false,
  policy_version: "ryde-policy-0.1.0",
  created_at: "2026-09-22T07:08:00Z",
  case_facts: {
    ride_id: "RIDE-000123",
    pickup: "Orchard Road, Singapore",
    dropoff: "Changi Airport T3, Singapore",
    planned_distance_km: 13.7,
    planned_duration_s: 1080,
    actual_distance_km: 18.4,
    actual_duration_s: 1620,
    surge_multiplier: 1.0,
    fare_cents: 2850,
    currency: "SGD",
  },
  evidence_audit: {
    findings: [
      {
        party: "driver",
        claim_text: "The trip followed the planned route.",
        classification: "contradicted",
        confidence: 0.92,
        explanation: "The recorded GPS distance is 18.4 km, compared with the planned 13.7 km.",
        evidence_references: ["EV-000789"],
        materiality: "material",
      },
    ],
    provider: { kind: "llm", display_name: "OpenAI", model: "gpt-4o" },
  },
  fraud_assessment: {
    risk_score: 0.65,
    confidence: 0.8,
    influence_weight: 2,
    findings: [
      {
        finding_type: "claim_evidence_mismatch",
        party: "driver",
        summary: "The route claim differs from the recorded GPS distance.",
        source_fields: ["route.actual_distance_km"],
        evidence_ids: ["EV-000789"],
      },
    ],
    provider: { kind: "llm", display_name: "OpenAI", model: "gpt-4o" },
  },
  model_proposed_ruling: null,
  reviewer_approved_ruling: null,
  advocates: {
    rider: {
      argument:
        "The driver deviated from the planned route, increasing the distance from 13.7 km to 18.4 km (34.2% above plan) without any rider-requested change, road closure, or safety justification. Under policy RP-ROUTE-003, this unjustified deviation above 15% entitles the rider to a refund of the excess fare attributable to the extra distance.",
      claims: [
        {
          text: "The actual distance of 18.4 km exceeds the planned 13.7 km by 34.2%, well above the 15% tolerance in RP-ROUTE-002.",
          citations: [
            {
              evidence_id: "EV-000789",
              field_path: "route.actual_distance_km",
              observed_value: 18.4,
              supports: "claim-1",
              valid: true,
            },
          ],
        },
        {
          text: "No rider-requested route change, road closure, or safety consideration was recorded for this trip.",
          citations: [
            {
              evidence_id: "EV-000790",
              field_path: "chat_log.messages",
              observed_value: "no_rider_route_change",
              supports: "claim-2",
              valid: true,
            },
          ],
        },
      ],
      policy_references: ["RP-ROUTE-002", "RP-ROUTE-003", "RP-FARE-001"],
      rejected_evidence: [
        {
          evidence_id: "EV-000791",
          reason: "Evidence submitted by driver does not contain a timestamp within the trip window; cannot establish that the road closure occurred during this ride.",
        },
      ],
      invalid_citation_count: 0,
      provider: {
        kind: "llm",
        display_name: "OpenAI",
        model: "gpt-4o",
        policy_version: "ryde-policy-0.1.0",
      },
    },
    driver: {
      argument:
        "The driver followed the route suggested by the navigation app, which recalculated due to a road closure on the original path. The deviation was not the driver's choice but a system-recommended detour. The fare charged reflects the actual distance travelled.",
      claims: [
        {
          text: "The navigation app recommended a detour due to a road closure on the original route.",
          citations: [
            {
              evidence_id: "EV-000790",
              field_path: "chat_log.messages",
              observed_value: "driver_nav_recalc",
              supports: "claim-1",
              valid: true,
            },
          ],
        },
      ],
      policy_references: ["RP-ROUTE-003"],
      rejected_evidence: [],
      invalid_citation_count: 0,
      provider: {
        kind: "llm",
        display_name: "OpenAI",
        model: "gpt-4o",
        policy_version: "ryde-policy-0.1.0",
      },
    },
  },
  judge: {
    ruling_type: "refund",
    recommended_action: {
      description: "Partial fare refund for excess distance attributable to unjustified route deviation",
      amount: {
        amount_cents: 325,
        currency: "SGD",
      },
    },
    confidence: 0.842,
    reasoning:
      "The actual distance of 18.4 km exceeds the planned 13.7 km by 34.2%, which is above the 15% tolerance defined in RP-ROUTE-002. Under RP-ROUTE-003, a deviation above 15% requires justification in the form of a rider-requested change, a road closure evidenced by conditions data, a safety consideration, or a pickup/dropoff adjustment. The driver cited a navigation app recommendation, but no road closure was evidenced by conditions data during the trip window (evidence EV-000791 was rejected for lacking a trip-window timestamp). The rider is entitled to a refund of the excess fare attributable to the extra distance under RP-FARE-001. The refund of S$3.25 represents the per-km rate applied to the 4.7 km excess.",
    evidence_references: ["EV-000789", "EV-000790"],
    decisive_facts: [
      { fact: "The actual route was 18.4 km rather than the planned 13.7 km.", evidence_references: ["EV-000789"] },
      { fact: "No recorded road closure justified the additional distance.", evidence_references: ["EV-000790"] },
    ],
    policy_references: ["RP-ROUTE-002", "RP-ROUTE-003", "RP-FARE-001"],
    precedent_references: ["DSP-001017"],
    precedent_binding: false,
    measurements: {
      deviation_pct: 34.2,
      planned_distance_km: 13.7,
      actual_distance_km: 18.4,
      excess_distance_km: 4.7,
    },
    escalation: {
      escalated: false,
      reasons: [],
      human_review_summary: null,
    },
    provider: {
      kind: "llm",
      display_name: "OpenAI",
      model: "gpt-4o",
      policy_version: "ryde-policy-0.1.0",
    },
  },
  external_findings: [],
  external_unavailable: false,
  urgency: 0.61,
  case_history: [
    {
      event: "filed",
      actor_type: "system",
      actor_id: null,
      at: "2026-09-22T07:08:00Z",
      payload: { category: "route_deviation", filed_by: "rider" },
    },
    {
      event: "adjudicated",
      actor_type: "agent",
      actor_id: "tribunal-v1",
      at: "2026-09-22T07:09:30Z",
      payload: { ruling_type: "refund", confidence: 0.842 },
    },
    {
      event: "resolved",
      actor_type: "agent",
      actor_id: "tribunal-v1",
      at: "2026-09-22T07:09:31Z",
      payload: { status: "resolved" },
    },
  ],
};
