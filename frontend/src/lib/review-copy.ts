import { formatDateTime } from "./api/format";

const fieldNames: Record<string, string> = {
  quoted_fare_cents: "Quoted fare", charged_fare_cents: "Charged fare", total_fare_cents: "Receipt total",
  cancellation_fee_cents: "Cancellation fee", waiting_fare_cents: "Waiting fee", amount_cents: "Amount",
  driver_waited_seconds: "Driver waiting time", driver_wait_seconds: "Driver waiting time",
  seconds_after_matching: "Time before cancellation", actual_duration_s: "Journey time", planned_duration_s: "Estimated journey time",
  actual_distance_km: "Recorded route", planned_distance_km: "Planned route", deviation_pct: "Distance difference",
  min_distance_to_pickup_m: "Closest recorded distance from pickup", accuracy_m: "Location accuracy",
  latitude: "Trip location", longitude: "Trip location", lat: "Trip location", lon: "Trip location",
  service_tier: "Service", cancellation_actor: "Cancelled by", cancellation_timestamp: "Cancelled at",
  accepted_at: "Driver matched", driver_arrival_at: "Driver arrival", arrival_at: "Driver arrival",
  completed_at: "Trip completed", booked_at: "Trip booked", scheduled_at: "Scheduled pickup",
  arrival_button_recorded: "Arrival confirmation", contact_attempt_recorded: "Contact attempt",
  fee_type: "Charge type", item_status: "Item status", category: "Dispute type", status: "Recorded status",
};
export function fieldLabel(path: string): string {
  const key = path.split(".").at(-1) ?? path;
  return fieldNames[key] ?? key.replaceAll("_", " ").replace(/^\w/, x => x.toUpperCase());
}
export function durationLabel(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "Not recorded";
  const seconds = Math.floor(value), minutes = Math.floor(seconds / 60), remainder = seconds % 60;
  return minutes ? `${minutes} min${remainder ? ` ${remainder} sec` : ""}` : `${seconds} sec`;
}
export function factValue(path: string, value: unknown): string {
  const key = path.split(".").at(-1) ?? path;
  if (value === null || value === undefined) return "Not recorded";
  if (typeof value === "object") return "Open evidence to inspect this record";
  if (["latitude", "longitude", "lat", "lon"].includes(key)) return "View location on map";
  if (typeof value === "boolean") return value ? "Recorded" : "Not recorded";
  if (key.endsWith("_cents") && typeof value === "number") return new Intl.NumberFormat("en-SG", { style: "currency", currency: "SGD" }).format(value / 100);
  if (key.endsWith("_seconds") || key.endsWith("_duration_s")) return durationLabel(value);
  if (typeof value === "string" && /(?:_at|_timestamp)$/.test(key) && !Number.isNaN(Date.parse(value))) return formatDateTime(value);
  if (typeof value === "number") return `${new Intl.NumberFormat("en-SG", { maximumFractionDigits: 2 }).format(value)}${key.endsWith("_km") ? " km" : key.endsWith("_m") ? " m" : key.endsWith("_pct") ? "%" : ""}`;
  const values: Record<string, string> = { rider: "Rider", driver: "Driver", rider_cancellation: "Rider cancellation fee", rider_waiting: "Rider waiting fee", driver_payout: "Driver payout" };
  return values[String(value)] ?? String(value).replaceAll("_", " ");
}
export const policyLabel = (id: string): string => ({
  "RY-CANCEL-001": "Cancellation timing", "RY-CANCEL-002": "Driver arrival and waiting", "RY-CANCEL-003": "Scheduled-trip cancellation",
  "RY-CANCEL-004": "Rider cancellation charge", "RY-WAIT-001": "Waiting charges", "RY-WAIT-002": "Rider waiting charge",
  "RY-WAIVER-001": "Cancellation voucher waiver", "RY-WAIVER-002": "Waiting-fee voucher waiver", "RY-SERVICE-001": "Service exclusions",
  "RY-ROUTE-001": "Route and quoted fare", "RY-FARE-001": "Fares and surcharges", "RY-FARE-002": "Receipt reconciliation", "RY-FARE-003": "Tolls and ERP",
  "RY-DRIVER-CANCEL-001": "Driver cancellation payout", "RY-DAMAGE-001": "Cleaning claim requirements", "RY-APPEAL-001": "Cleaning claim review",
  "RY-SAFETY-003": "Safety investigation", "RY-LOST-001": "Lost-item support", "RY-CONDUCT-001": "Conduct investigation",
  "TR-EVIDENCE-001": "Verified evidence", "TR-EVIDENCE-002": "Evidence conflicts", "TR-POLICY-001": "Unclear policy boundaries",
  "TR-REMEDY-001": "Supported remedies", "TR-PREC-001": "Use of past decisions", "TR-SAFETY-001": "Safety review",
  "TR-ESC-001": "When a reviewer is needed", "TR-TRACE-001": "Decision records", "TR-CATEGORY-001": "Cases requiring investigation",
} as Record<string, string>)[id] ?? "Policy guidance";

export function activityLabel(event: string): string {
  return ({ argument_completed: "Prepared a case", initial_review: "Checked the submissions", review_round: "Checked unresolved questions",
    advocate_repair_requested: "Requested more support", evidence_gap_check: "Checked available records", repair_completed: "Updated the submission",
    verification_completed: "Verified supporting records", audit_completed: "Checked evidence references", rules_first_review: "Applied published policy",
    repair_satisfied: "Resolved the evidence question", gemini_escalation: "Requested AI review", model_escalation: "Requested model review",
    human_review_without_model: "Requested human review", final_validation: "Checked the proposed decision", ruling_proposed: "Prepared an outcome",
    fallback: "AI review unavailable", human_review_required: "Human decision needed", risk_screen_completed: "Checked safety signals",
  } as Record<string, string>)[event] ?? "Recorded a review step";
}
