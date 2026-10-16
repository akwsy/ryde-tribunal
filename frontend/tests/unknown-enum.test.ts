import { describe, it, expect } from "vitest";
import {
  labelForRulingType,
  labelForVerificationStatus,
  labelForCaseStatus,
  labelForCategory,
  labelForEvidenceClass,
  labelForEscalationReason,
} from "@/lib/api/format";

describe("unknown enum fallback", () => {
  it("renders a safe fallback for an unknown ruling_type", () => {
    const result = labelForRulingType("unknown_ruling");
    expect(result).toContain("Unknown ruling type: unknown_ruling");
    expect(result).not.toThrow;
  });

  it("renders known ruling types correctly", () => {
    expect(labelForRulingType("refund")).toBe("Refund");
    expect(labelForRulingType("compensation")).toBe("Compensation");
    expect(labelForRulingType("no_action")).toBe("No Action");
  });

  it("renders a safe fallback for an unknown verification status", () => {
    const result = labelForVerificationStatus("bogus");
    expect(result).toContain("Unknown status: bogus");
  });

  it("renders a safe fallback for an unknown case status", () => {
    expect(labelForCaseStatus("weird")).toContain("Unknown status: weird");
  });

  it("renders a safe fallback for an unknown category", () => {
    expect(labelForCategory("not_a_category")).toContain("Unknown category: not_a_category");
  });

  it("labels the current filing categories, including the renamed no-show charge", () => {
    expect(labelForCategory("route_deviation")).toBe("Route Deviation");
    expect(labelForCategory("no_show_charge")).toBe("No-Show Charge");
    expect(labelForCategory("fare_calculation")).toBe("Fare Calculation");
    expect(labelForCategory("other_cancellation_fee")).toBe("Other Cancellation Fee");
    expect(labelForCategory("property_damage")).toBe("Property Damage");
    expect(labelForCategory("safety_incident")).toBe("Safety Incident");
    expect(labelForCategory("lost_item")).toBe("Lost Item");
    expect(labelForCategory("conduct_complaint")).toBe("Conduct Complaint");
  });

  it("renders a safe fallback for an unknown evidence class", () => {
    expect(labelForEvidenceClass("mystery")).toContain("Unknown evidence class: mystery");
  });

  it("labels imported app-event evidence", () => {
    expect(labelForEvidenceClass("app_event")).toBe("App Event");
  });

  it("renders a safe fallback for an unknown escalation reason", () => {
    expect(labelForEscalationReason("some_reason")).toContain("Unknown reason: some_reason");
  });

  it("explains common review reasons in plain language", () => {
    expect(labelForEscalationReason("confidence_below_threshold")).toBe("The available information does not give a clear answer");
    expect(labelForEscalationReason("contradictory_evidence")).toBe("The records disagree");
  });
});
