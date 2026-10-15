import type { PolicyDocument } from "@/lib/api/types";

/**
 * FIXTURE — not production data. All data is synthetic.
 * Historical synthetic policy fixture for UI tests only.
 */
export const policyDocument: PolicyDocument = {
  version: "ryde-policy-0.1.0",
  rules: [
    { id: "RP-FARE-001", text: "A rider is charged the fare quoted at booking unless the trip materially deviates from the quoted trip. Where a deviation is attributable to the driver, the rider is entitled to a refund of the excess over the quoted fare, not the whole fare.", category: "fare" },
    { id: "RP-FARE-002", text: "Surge pricing applied at booking is valid for the whole trip and is not itself grounds for a refund. A surge multiplier applied after booking is invalid.", category: "fare" },
    { id: "RP-ROUTE-002", text: "A deviation up to 15% of planned distance is within normal operating tolerance and is not overcharging.", category: "route_deviation" },
    { id: "RP-ROUTE-003", text: "A deviation above 15% requires justification. Unjustified deviation above 15% entitles the rider to a refund of the excess fare attributable to the extra distance.", category: "route_deviation" },
    { id: "RP-NOSHOW-001", text: "A cancellation fee is valid only where the driver arrived at the pickup point, waited the required 5 minutes after arrival, and attempted contact at least once.", category: "no_show_charge" },
    { id: "RP-NOSHOW-002", text: "Arrival means telemetry places the driver within 100 m of the pickup point. Where telemetry never places the driver within 100 m, the fee is invalid and fully refundable.", category: "no_show_charge" },
    { id: "RP-NOSHOW-004", text: "Where the driver waited less than 5 minutes or made no recorded contact attempt, the fee is invalid.", category: "no_show_charge" },
    { id: "RP-ESC-001", text: "Escalate when Judge confidence is below the approved threshold (0.70).", category: "escalation" },
    { id: "RP-ESC-005", text: "An escalated case carries a complete human-review summary: the question to decide, the evidence relied on, the conflict or gap that caused escalation, and what each advocate argued.", category: "escalation" },
  ],
};
