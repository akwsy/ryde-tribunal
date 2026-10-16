import { describe, expect, it } from "vitest";
import { durationLabel, factValue, fieldLabel } from "@/lib/review-copy";
describe("reviewer language preserves decisive values", () => {
  it("does not round a policy-sensitive duration across the three-minute boundary", () => {
    expect(durationLabel(179)).toBe("2 min 59 sec");
    expect(durationLabel(180)).toBe("3 min");
    expect(durationLabel(181)).toBe("3 min 1 sec");
  });
  it("shows currency and avoids JSON or object dumps", () => {
    expect(factValue("fare.cancellation_fee_cents", 661)).toBe(new Intl.NumberFormat("en-SG", {style:"currency",currency:"SGD"}).format(6.61));
    expect(factValue("record", { lat: 1.2 })).not.toMatch(/\[object|\{/);
    expect(factValue("latitude", 1.2)).toBe("View location on map");
  });
  it("names decisive facts and preserves missing evidence", () => {
    expect(fieldLabel("ride.cancellation_actor")).toBe("Cancelled by");
    expect(factValue("driver_waited_seconds", null)).toBe("Not recorded");
  });
});
