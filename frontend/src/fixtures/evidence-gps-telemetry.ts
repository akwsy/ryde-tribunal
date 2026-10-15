import type { Evidence } from "@/lib/api/types";

/**
 * FIXTURE — not production data. All data is synthetic.
 *
 * GPS telemetry evidence: verified, with uncertainty_pct present.
 * Shape from the API contract (Evidence).
 */
export const evidenceGpsTelemetry: Evidence = {
  evidence_id: "EV-000789",
  case_id: "DSP-000045",
  class: "gps_telemetry",
  source: "system_record",
  recorded_at: "2026-09-22T06:40:00Z",
  provenance: {
    table: "ride_gps_samples",
    row_ids: ["sample-001", "sample-002", "sample-003"],
    collector: "app_v3",
  },
  verification: {
    status: "verified",
    method: "device_gps_signed",
    uncertainty_pct: 2.5,
  },
  visibility: "both",
  payload: {
    route: {
      planned_distance_km: 13.7,
      actual_distance_km: 18.4,
      deviation_pct: 34.2,
      waypoints: [
        { lat: 1.3041, lng: 103.8319, label: "Orchard Road" },
        { lat: 1.3586, lng: 103.9899, label: "Changi Airport T3" },
      ],
    },
    samples: [
      { ts: "2026-09-22T06:40:00Z", lat: 1.3041, lng: 103.8319, accuracy_m: 3 },
      { ts: "2026-09-22T06:45:00Z", lat: 1.3120, lng: 103.8550, accuracy_m: 4 },
      { ts: "2026-09-22T06:50:00Z", lat: 1.3300, lng: 103.9000, accuracy_m: 3 },
      { ts: "2026-09-22T06:55:00Z", lat: 1.3586, lng: 103.9899, accuracy_m: 2 },
    ],
  },
};
