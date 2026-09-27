import type { CaseResult } from "@/lib/api/types";
import { caseResultResolved } from "./case-result-resolved";

/**
 * FIXTURE — not production data. All data is synthetic.
 *
 * Escalated case: confidence below threshold (0.6996 → 70.0% display,
 * but escalated because the raw value is below 0.70) and high impact.
 * Includes human_review_summary per RP-ESC-005.
 */
export const caseResultEscalated: CaseResult = {
  ...caseResultResolved,
  case_id: "DSP-000047",
  status: "escalated",
  synthetic_reasoning: false,
  created_at: "2026-09-22T07:12:00Z",
  judge: {
    ...caseResultResolved.judge!,
    confidence: 0.6996,
    reasoning:
      "The actual distance exceeds the planned distance by 34.2%. However, the driver submitted evidence of a road closure (EV-000791), which was rejected for lacking a trip-window timestamp but may indicate a genuine diversion. The rider's claim and the driver's defense are partially contradictory, and confidence is below the 0.70 threshold. Escalating to human review.",
    escalation: {
      escalated: true,
      reasons: ["confidence_below_threshold", "high_impact", "contradictory_evidence"],
      human_review_summary:
        "Question to decide: whether the route deviation was justified by a road closure. " +
        "Evidence relied on: GPS telemetry (EV-000789) showing 34.2% deviation; chat log (EV-000790) " +
        "showing no rider-requested change; driver-submitted evidence (EV-000791) of a road closure, " +
        "rejected for lacking a trip-window timestamp. Conflict: the driver claims a system-recommended " +
        "detour, but the submitted closure evidence does not cover the trip window. The rider argues " +
        "the deviation was unjustified; the driver argues it was system-directed. Recommend reviewing " +
        "the navigation app's route recalculation log and any road closure data for the trip's time window.",
    },
    provider: {
      kind: "llm",
      model: "gpt-4o",
      policy_version: "ryde-policy-0.1.0",
    },
  },
  urgency: 0.85,
  case_history: [
    {
      event: "filed",
      actor_type: "system",
      actor_id: null,
      at: "2026-09-22T07:12:00Z",
      payload: { category: "route_deviation", filed_by: "rider" },
    },
    {
      event: "adjudicated",
      actor_type: "agent",
      actor_id: "tribunal-v1",
      at: "2026-09-22T07:13:30Z",
      payload: { ruling_type: "refund", confidence: 0.6996 },
    },
    {
      event: "escalated",
      actor_type: "agent",
      actor_id: "tribunal-v1",
      at: "2026-09-22T07:13:31Z",
      payload: {
        status: "escalated",
        reasons: ["confidence_below_threshold", "high_impact", "contradictory_evidence"],
      },
    },
  ],
};
