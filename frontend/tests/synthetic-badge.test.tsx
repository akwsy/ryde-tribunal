import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SyntheticBadge } from "@/components/synthetic-badge";

describe("SyntheticBadge", () => {
  it("renders the badge when synthetic_reasoning is true", () => {
    render(<SyntheticBadge show={true} />);
    const badge = screen.getByTestId("synthetic-reasoning-badge");
    expect(badge).toBeVisible();
    expect(badge).toHaveTextContent("Synthetic Reasoning");
    expect(badge).toHaveAttribute("role", "status");
  });

  it("does not render the badge when synthetic_reasoning is false", () => {
    const { container } = render(<SyntheticBadge show={false} />);
    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId("synthetic-reasoning-badge")).not.toBeInTheDocument();
  });

  it("has an accessible aria-label explaining the badge", () => {
    render(<SyntheticBadge show={true} />);
    const badge = screen.getByTestId("synthetic-reasoning-badge");
    expect(badge).toHaveAttribute(
      "aria-label",
      expect.stringContaining("scripted fallback"),
    );
  });

  it("renders at small size", () => {
    render(<SyntheticBadge show={true} size="sm" />);
    const badge = screen.getByTestId("synthetic-reasoning-badge");
    expect(badge).toBeVisible();
  });
});
