import { describe, it, expect } from "vitest";
import { formatConfidence, formatConfidenceA11y } from "@/lib/api/format";

describe("confidence formatting", () => {
  it("formats 0.842 as 84.2%", () => {
    expect(formatConfidence(0.842)).toBe("84.2%");
  });

  it("formats 0.700 as 70.0%", () => {
    expect(formatConfidence(0.7)).toBe("70.0%");
  });

  it("formats 0.6996 as 70.0% (the hazard case)", () => {
    // 0.6996 rounds to 70.0% but does NOT clear the 0.70 threshold.
    // The UI must not derive escalation from this — it must use
    // judge.escalation.escalated, which is authoritative.
    expect(formatConfidence(0.6996)).toBe("70.0%");
  });

  it("formats 1.000 as 100.0%", () => {
    expect(formatConfidence(1.0)).toBe("100.0%");
  });

  it("formats 0.000 as 0.0%", () => {
    expect(formatConfidence(0)).toBe("0.0%");
  });

  it("includes the raw float in the a11y label", () => {
    const label = formatConfidenceA11y(0.842);
    expect(label).toContain("0.842");
    expect(label).toContain("84.2%");
  });
});
