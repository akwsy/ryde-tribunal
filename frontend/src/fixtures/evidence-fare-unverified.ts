import type { Evidence } from "@/lib/api/types";

/**
 * FIXTURE — not production data. All data is synthetic.
 *
 * Fare evidence: unverified, with uncertainty_pct present at a higher value.
 * Tests the unverified + uncertainty rendering path.
 */
export const evidenceFareUnverified: Evidence = {
  evidence_id: "EV-000792",
  case_id: "DSP-000045",
  class: "fare",
  source: "driver_submitted",
  recorded_at: "2026-09-22T07:05:00Z",
  provenance: {
    table: "driver_submissions",
    row_ids: ["sub-001"],
    collector: "driver_app_v2",
  },
  verification: {
    status: "unverified",
    method: null,
    uncertainty_pct: 15.0,
  },
  visibility: "reviewer_only",
  payload: {
    fare_cents: 2850,
    currency: "SGD",
    components: {
      base_fare: 2500,
      distance: 350,
      time: 0,
      surge: 0,
      promo: 0,
      cancellation_fee: 0,
    },
    notes: "Driver-submitted fare record without system ledger match.",
  },
};
