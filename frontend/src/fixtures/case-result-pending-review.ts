import type { CaseResult } from "@/lib/api/types";

/** Synthetic fixture for an allowlisted category awaiting human review. */
export const caseResultPendingReview: CaseResult = {
  case_id: "DSP-000049",
  case_source: "live",
  ride_id: "RIDE-000125",
  category: "lost_item",
  status: "pending_review",
  synthetic: true,
  synthetic_reasoning: false,
  policy_version: "ryde-policy-0.1.0",
  created_at: "2026-09-23T08:15:00Z",
  case_facts: { ride_id: "RIDE-000125" },
  evidence_audit: null,
  fraud_assessment: null,
  advocates: null,
  judge: null,
  model_proposed_ruling: null,
  reviewer_approved_ruling: null,
  human_review_summary: "A reviewer must assess the reported lost item and available trip records.",
  external_findings: [],
  external_unavailable: false,
  urgency: 0.35,
  case_history: [
    {
      event: "filed",
      actor_type: "system",
      actor_id: null,
      at: "2026-09-23T08:15:00Z",
      payload: { category: "lost_item", filed_by: "rider" },
    },
  ],
};
