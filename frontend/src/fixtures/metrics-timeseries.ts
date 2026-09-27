import type { MetricsTimeseries } from "@/lib/api/types";

/**
 * FIXTURE — not production data. All data is synthetic.
 * Phase One placeholder — not used in Phase Zero components.
 */
export const metricsTimeseries: MetricsTimeseries = {
  timezone: "Asia/Singapore",
  granularity: "day",
  group_by: "category",
  points: [
    { date: "2026-09-16", series: [{ key: "route_deviation", count: 5 }, { key: "no_show_charge", count: 1 }] },
    { date: "2026-09-17", series: [{ key: "route_deviation", count: 7 }] },
    { date: "2026-09-18", series: [{ key: "route_deviation", count: 6 }, { key: "no_show_charge", count: 2 }] },
    { date: "2026-09-19", series: [{ key: "route_deviation", count: 8 }, { key: "no_show_charge", count: 1 }] },
    { date: "2026-09-20", series: [{ key: "route_deviation", count: 4 }, { key: "no_show_charge", count: 3 }] },
    { date: "2026-09-21", series: [{ key: "route_deviation", count: 9 }] },
    { date: "2026-09-22", series: [{ key: "route_deviation", count: 7 }, { key: "no_show_charge", count: 2 }] },
  ],
};
