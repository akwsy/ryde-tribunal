import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MoneyDisplay } from "@/components/money-display";

// The currency symbol depends on ICU data; the amount must be correct.

describe("MoneyDisplay", () => {
  it("renders 325 SGD with amount 3.25", () => {
    render(<MoneyDisplay money={{ amount_cents: 325, currency: "SGD" }} />);
    const el = screen.getByTestId("money-display");
    expect(el).toHaveTextContent("3.25");
    expect(el).toHaveAttribute("data-amount-cents", "325");
    expect(el).toHaveAttribute("data-currency", "SGD");
  });

  it("renders 0 SGD with amount 0.00", () => {
    render(<MoneyDisplay money={{ amount_cents: 0, currency: "SGD" }} />);
    expect(screen.getByTestId("money-display")).toHaveTextContent("0.00");
  });

  it("renders a large value", () => {
    render(<MoneyDisplay money={{ amount_cents: 250000, currency: "SGD" }} />);
    expect(screen.getByTestId("money-display")).toHaveTextContent("2,500.00");
  });

  it("renders null amount gracefully", () => {
    render(<MoneyDisplay money={null} />);
    expect(screen.getByText("No amount specified")).toBeInTheDocument();
  });

  it("has an aria-label with the raw cents value", () => {
    render(<MoneyDisplay money={{ amount_cents: 325, currency: "SGD" }} />);
    const el = screen.getByTestId("money-display");
    expect(el).toHaveAttribute("aria-label", expect.stringContaining("325"));
    expect(el).toHaveAttribute("aria-label", expect.stringContaining("SGD"));
  });
});
