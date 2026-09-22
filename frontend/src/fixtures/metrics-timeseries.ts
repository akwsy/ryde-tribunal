import type { MetricsTimeseries } from "@/lib/api/types";

/**
 * FIXTURE — not production data. All data is synthetic.
 * Phase One placeholder — not used in Phase Zero components.
 */
export const metricsTimeseries: MetricsTimeseries = {
  points: [
    { date: "2026-09-16", automatic: 5, human_intervention: 1 },
    { date: "2026-09-17", automatic: 7, human_intervention: 0 },
    { date: "2026-09-18", automatic: 6, human_intervention: 2 },
    { date: "2026-09-19", automatic: 8, human_intervention: 1 },
    { date: "2026-09-20", automatic: 4, human_intervention: 3 },
    { date: "2026-09-21", automatic: 9, human_intervention: 0 },
    { date: "2026-09-22", automatic: 7, human_intervention: 2 },
  ],
};
