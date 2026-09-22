import type { MetricsOverview } from "@/lib/api/types";

/**
 * FIXTURE — not production data. All data is synthetic.
 * Phase One placeholder — not used in Phase Zero components.
 */
export const metricsOverview: MetricsOverview = {
  filed: { today: 3, week: 22, month: 87 },
  auto_resolved: 18,
  human_review_pending: 4,
  overridden: 2,
};
