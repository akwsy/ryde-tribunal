import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { CaseView } from "@/components/case-view";
import { caseResultResolved } from "@/fixtures/case-result-resolved";
import { caseResultSynthetic } from "@/fixtures/case-result-synthetic";
import { caseResultEscalated } from "@/fixtures/case-result-escalated";
import { errorNotFound, errorDatabaseUnavailable } from "@/fixtures/errors";
import { ApiError } from "@/lib/api/client";

// Mock the active client. The mock factory creates a client that returns
// fixture data based on the case ID, simulating the FixtureClient.
const mockGetDispute = vi.fn(async (caseId: string) => {
  switch (caseId) {
    case "DSP-000045":
      return caseResultResolved;
    case "DSP-000046":
      return caseResultSynthetic;
    case "DSP-000047":
      return caseResultEscalated;
    case "DSP-000999":
      throw new ApiError(404, "not_found", "Case not found.", errorNotFound.error.details);
    case "DSP-000050":
      throw new ApiError(503, "database_unavailable", "Database unavailable.", errorDatabaseUnavailable.error.details);
    default:
      throw new ApiError(404, "not_found", "Case not found.");
  }
});

vi.mock("@/lib/api/fixture-client", () => ({
  getActiveClient: () => ({ getDispute: mockGetDispute }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    getClient: () => ({ getDispute: mockGetDispute }),
  };
});

describe("CaseView", () => {
  it("loads from a fixture response and displays case details", async () => {
    render(<CaseView caseId="DSP-000045" />);

    expect(screen.getByTestId("loading-state")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("case-details")).toBeInTheDocument();
    });

    expect(screen.getByTestId("case-id")).toHaveTextContent("DSP-000045");
    // Ride ID is displayed in the header (font-mono span, not the JSON pre)
    const rideIdElements = screen.getAllByText(/RIDE-000123/);
    expect(rideIdElements.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId("advocate-panel-rider")).toBeInTheDocument();
    expect(screen.getByTestId("advocate-panel-driver")).toBeInTheDocument();
    expect(screen.getByTestId("judge-ruling")).toBeInTheDocument();
    expect(screen.getByTestId("confidence-display")).toBeInTheDocument();
  });

  it("displays no synthetic badge when synthetic_reasoning is false", async () => {
    render(<CaseView caseId="DSP-000045" />);
    await waitFor(() => {
      expect(screen.getByTestId("case-details")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("synthetic-reasoning-badge")).not.toBeInTheDocument();
  });

  it("displays the synthetic badge when synthetic_reasoning is true", async () => {
    render(<CaseView caseId="DSP-000046" />);
    await waitFor(() => {
      expect(screen.getByTestId("case-details")).toBeInTheDocument();
    });
    // When synthetic_reasoning is true, badges appear in multiple places
    // (case header, advocate panels, judge ruling). At least one must be visible.
    const badges = screen.getAllByTestId("synthetic-reasoning-badge");
    expect(badges.length).toBeGreaterThanOrEqual(1);
    expect(badges[0]).toBeVisible();
  });

  it("renders the escalation state when escalated", async () => {
    render(<CaseView caseId="DSP-000047" />);
    await waitFor(() => {
      expect(screen.getByTestId("case-details")).toBeInTheDocument();
    });
    const escalation = screen.getByTestId("escalation-state");
    expect(escalation).toHaveAttribute("role", "alert");
    expect(screen.getByText("Human Review Summary")).toBeInTheDocument();
  });

  it("renders the empty state for a not-found case", async () => {
    render(<CaseView caseId="DSP-000999" />);
    await waitFor(() => {
      expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    });
    expect(screen.getByText("Case Not Found")).toBeInTheDocument();
    expect(screen.getByText(/DSP-000999/)).toBeInTheDocument();
  });

  it("renders the error state for a database_unavailable error (503)", async () => {
    render(<CaseView caseId="DSP-000050" />);
    await waitFor(() => {
      expect(screen.getByTestId("error-state")).toBeInTheDocument();
    });
    const errorState = screen.getByTestId("error-state");
    expect(errorState).toHaveAttribute("data-error-code", "database_unavailable");
    expect(errorState).toHaveAttribute("data-error-status", "503");
    expect(screen.getByText("Database Unavailable")).toBeInTheDocument();
  });

  it("renders money from amount_cents", async () => {
    render(<CaseView caseId="DSP-000045" />);
    await waitFor(() => {
      expect(screen.getByTestId("case-details")).toBeInTheDocument();
    });
    const moneyEl = screen.getByTestId("money-display");
    expect(moneyEl).toHaveTextContent("3.25");
    expect(moneyEl).toHaveAttribute("data-amount-cents", "325");
  });

  it("renders confidence as a percentage", async () => {
    render(<CaseView caseId="DSP-000045" />);
    await waitFor(() => {
      expect(screen.getByTestId("case-details")).toBeInTheDocument();
    });
    expect(screen.getByTestId("confidence-display")).toHaveTextContent("84.2%");
  });
});
