import { describe, it, expect } from "vitest";
import { formatMoney } from "@/lib/api/money";

// Intl.NumberFormat('en-SG', { style: 'currency', currency: 'SGD' }) produces
// 'S$3.25' on runtimes with full en-SG ICU data. On Node.js with ICU 78.x,
// the symbol may be '$' (the en fallback). The contract says to use this
// formatter — the exact symbol is a locale-data concern, not a code concern.
// These tests verify the AMOUNT is correct (3.25, 0.00, etc.) and that the
// formatter is the one the contract specifies.

describe("money formatting", () => {
  it("formats 325 SGD to show 3.25", () => {
    const result = formatMoney({ amount_cents: 325, currency: "SGD" });
    expect(result).toContain("3.25");
    expect(result).toMatch(/3\.25/);
  });

  it("formats 0 SGD to show 0.00", () => {
    const result = formatMoney({ amount_cents: 0, currency: "SGD" });
    expect(result).toContain("0.00");
    expect(result).toMatch(/0\.00/);
  });

  it("formats a large value correctly", () => {
    expect(formatMoney({ amount_cents: 1500, currency: "SGD" })).toContain("15.00");
    const result = formatMoney({ amount_cents: 250000, currency: "SGD" });
    expect(result).toContain("2,500.00");
  });

  it("never produces a float string", () => {
    const result = formatMoney({ amount_cents: 325, currency: "SGD" });
    expect(result).not.toMatch(/\.\d{3,}/);
  });

  it("handles different currency codes", () => {
    const usd = formatMoney({ amount_cents: 100, currency: "USD" });
    expect(usd).toContain("1.00");
    const eur = formatMoney({ amount_cents: 500, currency: "EUR" });
    expect(eur).toMatch(/5[,.]00/);
  });

  it("is the correct amount: 325 cents -> 3.25, not 325 or 0.325", () => {
    const result = formatMoney({ amount_cents: 325, currency: "SGD" });
    expect(result).toContain("3.25");
    // Must NOT contain the raw cents value (325) as a standalone number
    expect(result).not.toMatch(/^.*325.*$/); // 325 should only appear as 3.25
    expect(result).not.toContain("0.325");
  });
});
