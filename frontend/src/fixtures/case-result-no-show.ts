import type { CaseResult } from "@/lib/api/types";

/**
 * FIXTURE — not production data. All data is synthetic.
 *
 * No-show case: driver never arrived at pickup, cancellation fee is invalid.
 */
export const caseResultNoShow: CaseResult = {
  case_id: "DSP-000048",
  ride_id: "RIDE-000124",
  category: "no_show",
  status: "resolved",
  synthetic: true,
  synthetic_reasoning: false,
  policy_version: "ryde-policy-0.1.0",
  created_at: "2026-09-22T08:15:00Z",
  case_facts: {
    ride_id: "RIDE-000124",
    pickup: "Tampines Mall, Singapore",
    dropoff: "Marina Bay Sands, Singapore",
    cancellation_fee_cents: 500,
    currency: "SGD",
    driver_arrived: false,
    driver_wait_time_s: 0,
    contact_attempts: 0,
  },
  advocates: {
    rider: {
      argument:
        "The driver never arrived at the pickup point. GPS telemetry shows no position within 100 m of the pickup at any time. The driver made no contact attempt via call or chat. Under RP-NOSHOW-002 and RP-NOSHOW-004, the cancellation fee is invalid and fully refundable.",
      claims: [
        {
          text: "The driver was never within 100 m of the pickup point.",
          citations: [
            {
              evidence_id: "EV-000789",
              field_path: "gps.min_distance_to_pickup_m",
              observed_value: 850,
              supports: "claim-1",
              valid: true,
            },
          ],
        },
        {
          text: "No call or chat message was attempted by the driver.",
          citations: [
            {
              evidence_id: "EV-000790",
              field_path: "chat_log.message_count",
              observed_value: 0,
              supports: "claim-2",
              valid: true,
            },
          ],
        },
      ],
      policy_references: ["RP-NOSHOW-001", "RP-NOSHOW-002", "RP-NOSHOW-004"],
      rejected_evidence: [],
      invalid_citation_count: 0,
      provider: {
        kind: "llm",
        model: "gpt-4o",
        policy_version: "ryde-policy-0.1.0",
      },
    },
    driver: {
      argument:
        "The driver attempted to reach the pickup but encountered heavy traffic. The driver arrived after the rider had already cancelled. The cancellation fee should apply.",
      claims: [
        {
          text: "The driver was en route but delayed by traffic.",
          citations: [],
        },
      ],
      policy_references: ["RP-NOSHOW-001"],
      rejected_evidence: [],
      invalid_citation_count: 1,
      provider: {
        kind: "llm",
        model: "gpt-4o",
        policy_version: "ryde-policy-0.1.0",
      },
    },
  },
  judge: {
    ruling_type: "refund",
    recommended_action: {
      description: "Full refund of invalid cancellation fee",
      amount: {
        amount_cents: 500,
        currency: "SGD",
      },
    },
    confidence: 0.918,
    reasoning:
      "GPS telemetry places the driver's closest position at 850 m from the pickup point, never within the 100 m radius required by RP-NOSHOW-002. No contact attempt was recorded in the chat log. Under RP-NOSHOW-004, where the driver waited less than 5 minutes or made no recorded contact attempt, the fee is invalid. The cancellation fee of S$5.00 is fully refundable.",
    evidence_references: ["EV-000789", "EV-000790"],
    policy_references: ["RP-NOSHOW-001", "RP-NOSHOW-002", "RP-NOSHOW-004"],
    precedent_references: [],
    precedent_binding: false,
    measurements: {
      min_distance_to_pickup_m: 850,
      driver_wait_time_s: 0,
      contact_attempts: 0,
    },
    escalation: {
      escalated: false,
      reasons: [],
      human_review_summary: null,
    },
    provider: {
      kind: "llm",
      model: "gpt-4o",
      policy_version: "ryde-policy-0.1.0",
    },
  },
  external_findings: [],
  external_unavailable: false,
  urgency: 0.45,
  case_history: [
    {
      event: "filed",
      actor_type: "system",
      actor_id: null,
      at: "2026-09-22T08:15:00Z",
      payload: { category: "no_show", filed_by: "rider" },
    },
    {
      event: "adjudicated",
      actor_type: "agent",
      actor_id: "tribunal-v1",
      at: "2026-09-22T08:16:30Z",
      payload: { ruling_type: "refund", confidence: 0.918 },
    },
  ],
};
