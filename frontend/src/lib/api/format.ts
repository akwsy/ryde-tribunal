/**
 * Format a confidence float (0.000–1.000) as a percentage to one decimal.
 *
 * Display contract:
 * - 0.842 → "84.2%"
 * - Keep the raw float available in a tooltip/aria-label.
 *
 * HAZARD: Do NOT derive the escalation state by comparing this percentage
 * or the raw float to the 0.70 threshold. Use judge.escalation.escalated,
 * which is authoritative. 0.6996 rounds to 70.0% but does not clear the bar.
 */
export function formatConfidence(confidence: number): string {
  const pct = (confidence * 100).toFixed(1);
  return `${pct}%`;
}

/**
 * Format the raw float for a tooltip/aria-label so a reviewer sees the exact value.
 */
export function formatConfidenceA11y(confidence: number): string {
  return `Confidence: ${confidence.toFixed(3)} (displayed as ${formatConfidence(confidence)})`;
}

/**
 * Format an ISO-8601 UTC timestamp for display.
 */
export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Singapore",
  }).format(new Date(iso));
}

/**
 * Human-readable labels for enum values, with safe fallback for unknown values.
 * If the value is not in the known set, the function returns a safe fallback
 * string rather than throwing.
 */
export function labelForRulingType(value: string): string {
  const labels: Record<string, string> = {
    refund: "Refund",
    compensation: "Compensation",
    no_action: "No Action",
  };
  return labels[value] ?? `Unknown ruling type: ${value}`;
}

export function labelForVerificationStatus(value: string): string {
  const labels: Record<string, string> = {
    verified: "Verified",
    unverified: "Unverified",
    disputed: "Disputed",
    unverifiable: "Unverifiable",
  };
  return labels[value] ?? `Unknown status: ${value}`;
}

export function labelForCaseStatus(value: string): string {
  const labels: Record<string, string> = {
    queued: "Queued",
    processing: "Under review",
    resolved: "Resolved",
    escalated: "Escalated",
    pending_review: "Pending Review",
    overridden: "Overridden",
  };
  return labels[value] ?? `Unknown status: ${value}`;
}

export function labelForCategory(value: string): string {
  const labels: Record<string, string> = {
    route_deviation: "Route Deviation",
    no_show_charge: "No-Show Charge",
    fare_calculation: "Fare Calculation",
    other_cancellation_fee: "Other Cancellation Fee",
    property_damage: "Property Damage",
    safety_incident: "Safety Incident",
    lost_item: "Lost Item",
    conduct_complaint: "Conduct Complaint",
  };
  return labels[value] ?? `Unknown category: ${value}`;
}

export function labelForEvidenceClass(value: string): string {
  const labels: Record<string, string> = {
    gps_telemetry: "GPS Telemetry",
    chat_log: "Chat Log",
    app_event: "App Event",
    fare: "Fare",
    profile_history: "Profile History",
    attachment: "Attachment",
    external: "External",
  };
  return labels[value] ?? `Unknown evidence class: ${value}`;
}

export function labelForEscalationReason(value: string): string {
  const labels: Record<string, string> = {
    confidence_below_threshold: "The available information does not give a clear answer",
    materially_uncertain: "Important facts remain uncertain",
    contradictory_evidence: "The records disagree",
    insufficient_evidence: "Key records are missing",
    inaccurate_evidence: "Some evidence could not be confirmed",
    high_impact: "The possible amount needs a closer review",
    safety_category: "Safety cases need a human reviewer",
    exceeds_ruling_cap: "The amount is outside the automatic decision limit",
    fraud_risk: "A possible fraud concern needs a human reviewer",
  };
  return labels[value] ?? `Unknown reason: ${value}`;
}
