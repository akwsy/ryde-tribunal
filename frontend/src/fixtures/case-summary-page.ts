import type { CaseSummaryPage } from "@/lib/api/types";

/**
 * FIXTURE — not production data. All data is synthetic.
 *
 * Phase One placeholder fixture — not used in Phase Zero components,
 * but available so the Phase One dashboard extends without rewrite.
 */
export const caseSummaryPage: CaseSummaryPage = {
  items: [
    {
      case_id: "DSP-000045",
      ride_id: "RIDE-000123",
      category: "route_deviation",
      status: "resolved",
      confidence: 0.842,
      ruling_type: "refund",
      urgency: 0.61,
      needs_review: false,
      created_at: "2026-09-22T07:08:00Z",
      synthetic_reasoning: false,
    },
    {
      case_id: "DSP-000047",
      ride_id: "RIDE-000123",
      category: "route_deviation",
      status: "escalated",
      confidence: 0.6996,
      ruling_type: "refund",
      urgency: 0.85,
      needs_review: true,
      created_at: "2026-09-22T07:12:00Z",
      synthetic_reasoning: false,
    },
    {
      case_id: "DSP-000046",
      ride_id: "RIDE-000123",
      category: "route_deviation",
      status: "resolved",
      confidence: 0.842,
      ruling_type: "refund",
      urgency: 0.61,
      needs_review: false,
      created_at: "2026-09-22T07:10:00Z",
      synthetic_reasoning: true,
    },
    {
      case_id: "DSP-000048",
      ride_id: "RIDE-000124",
      category: "no_show",
      status: "resolved",
      confidence: 0.918,
      ruling_type: "refund",
      urgency: 0.45,
      needs_review: false,
      created_at: "2026-09-22T08:15:00Z",
      synthetic_reasoning: false,
    },
  ],
  next_cursor: null,
};
