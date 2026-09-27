import { describe, expect, it } from "vitest";
import { presetRange, singaporeBoundary, singaporeToday } from "@/lib/dashboard-dates";

describe("dashboard Singapore date ranges", () => {
  it("uses inclusive day, Sunday-start week, and current-month ranges", () => {
    expect(presetRange("day", "2026-09-25")).toEqual({ from: "2026-09-25", to: "2026-09-25" });
    expect(presetRange("week", "2026-09-25")).toEqual({ from: "2026-09-20", to: "2026-09-25" });
    expect(presetRange("month", "2026-09-25")).toEqual({ from: "2026-09-01", to: "2026-09-25" });
  });

  it("formats list boundaries in Singapore time and reads today's date there", () => {
    expect(singaporeBoundary("2026-09-25")).toBe("2026-09-25T00:00:00+08:00");
    expect(singaporeBoundary("2026-09-25", true)).toBe("2026-09-25T23:59:59.999+08:00");
    expect(singaporeToday(new Date("2026-09-24T18:00:00.000Z"))).toBe("2026-09-25");
  });
});
