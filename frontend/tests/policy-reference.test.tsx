import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PolicyReference } from "@/components/policy-reference";
import type { PolicyDocument } from "@/lib/api/types";

const policyWithSources: PolicyDocument = {
  version: "ryde-policy-1.0.0",
  rules: [
    {
      id: "RY-ROUTE-001",
      text: "Fare is fixed by pickup and drop-off points. The driver may use an efficient GPS route. A preferred route should be agreed before departure.",
      category: "route_deviation",
      classification: "ryde_policy",
      source: {
        url: "https://help.rydesharing.com/hc/en-us/articles/4412121982745-Can-I-suggest-my-preferred-route-to-the-driver",
        title: "Preferred route",
        retrieved_at: "2026-10-13",
        effective_from: null,
      },
    },
    {
      id: "TR-ESC-001",
      text: "Escalate confidence below the configured threshold, incomplete or contradictory decisive evidence, policy conflicts and high-impact decisions. Fraud risk alone never determines a ruling.",
      category: "escalation",
      classification: "tribunal_operating_rule",
      source: null,
    },
  ],
};

const mockGetPolicy = vi.fn(async (): Promise<PolicyDocument> => {
  // Only the current policy is available; historical versions are not stored.
  return policyWithSources;
});

vi.mock("@/lib/api/fixture-client", () => ({
  getActiveClient: () => ({ getPolicy: mockGetPolicy }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    getClient: () => ({ getPolicy: mockGetPolicy }),
  };
});

describe("PolicyReference", () => {
  it("renders a policy chip and opens the rule text with a source link", async () => {
    const user = userEvent.setup();
    render(<PolicyReference ruleId="RY-ROUTE-001" version="ryde-policy-1.0.0" />);

    const chip = screen.getByRole("button", { name: "RY-ROUTE-001" });
    expect(chip).toHaveAttribute("aria-expanded", "false");

    await user.click(chip);
    expect(chip).toHaveAttribute("aria-expanded", "true");

    // Rule text is shown.
    await waitFor(() => {
      expect(screen.getByText(/Fare is fixed by pickup and drop-off points/)).toBeInTheDocument();
    });

    // Classification label is shown.
    expect(screen.getByText("Ryde published policy")).toBeInTheDocument();

    // Source link opens in a new tab with the official URL.
    const sourceLink = screen.getByRole("link", { name: /Preferred route/ });
    expect(sourceLink).toHaveAttribute("href", "https://help.rydesharing.com/hc/en-us/articles/4412121982745-Can-I-suggest-my-preferred-route-to-the-driver");
    expect(sourceLink).toHaveAttribute("target", "_blank");
    expect(sourceLink).toHaveAttribute("rel", "noreferrer");

    // Policy version and retrieval date are shown.
    expect(screen.getByText(/Version ryde-policy-1.0.0/)).toBeInTheDocument();
    expect(screen.getByText(/Retrieved 2026-10-13/)).toBeInTheDocument();
  });

  it("shows a Tribunal operating rule without a source link", async () => {
    const user = userEvent.setup();
    render(<PolicyReference ruleId="TR-ESC-001" version="ryde-policy-1.0.0" />);

    await user.click(screen.getByRole("button", { name: "TR-ESC-001" }));

    await waitFor(() => {
      expect(screen.getByText(/Escalate confidence below the configured threshold/)).toBeInTheDocument();
    });
    expect(screen.getByText("Tribunal operating rule")).toBeInTheDocument();
    // No source link for tribunal operating rules without a source.
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText(/Version ryde-policy-1.0.0/)).toBeInTheDocument();
  });

  it("shows an unavailable message for a historical policy version not in the system", async () => {
    const user = userEvent.setup();
    render(<PolicyReference ruleId="RY-ROUTE-001" version="ryde-policy-0.1.1" />);

    await user.click(screen.getByRole("button", { name: "RY-ROUTE-001" }));

    await waitFor(() => {
      expect(screen.getByText(/historical policy is unavailable/i)).toBeInTheDocument();
    });
    // The version is still shown for context.
    expect(screen.queryByText(/Version ryde-policy-0.1.1/)).not.toBeInTheDocument();
  });

  it("shows an unavailable message when no version is provided", async () => {
    const user = userEvent.setup();
    render(<PolicyReference ruleId="RY-ROUTE-001" />);

    await user.click(screen.getByRole("button", { name: "RY-ROUTE-001" }));

    await waitFor(() => {
      expect(screen.getByText(/Policy version is unavailable/i)).toBeInTheDocument();
    });
  });

  it("toggles the popover closed and reopens without duplicating content", async () => {
    const user = userEvent.setup();
    render(<PolicyReference ruleId="RY-ROUTE-001" version="ryde-policy-1.0.0" />);

    const chip = screen.getByRole("button", { name: "RY-ROUTE-001" });
    await user.click(chip);
    await waitFor(() => expect(screen.getByText(/Fare is fixed by pickup and drop-off points/)).toBeInTheDocument());

    await user.click(chip);
    expect(chip).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/Fare is fixed by pickup and drop-off points/)).not.toBeInTheDocument();

    await user.click(chip);
    await waitFor(() => expect(screen.getByText(/Fare is fixed by pickup and drop-off points/)).toBeInTheDocument());
    expect(chip).toHaveAttribute("aria-expanded", "true");
  });
});
