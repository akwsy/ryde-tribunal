import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { CaseView } from "@/components/case-view";
import { caseResultResolved } from "@/fixtures/case-result-resolved";
import { caseResultEscalated } from "@/fixtures/case-result-escalated";
import { errorNotFound, errorDatabaseUnavailable } from "@/fixtures/errors";
import { ApiError } from "@/lib/api/client";

const mockGetDispute = vi.fn(async (caseId: string) => {
  switch (caseId) {
    case "DSP-000045":
      return caseResultResolved;
    case "DSP-000047":
      return caseResultEscalated;
    case "DSP-000999":
      throw new ApiError(404, "not_found", "Case not found.");
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

describe("state surfaces", () => {
  it("renders a distinct loading state", async () => {
    render(<CaseView caseId="DSP-000045" />);
    const loading = screen.getByTestId("loading-state");
    expect(loading).toBeInTheDocument();
    expect(loading).toHaveAttribute("aria-busy", "true");
  });

  it("renders a distinct empty state for not-found", async () => {
    render(<CaseView caseId="DSP-000999" />);
    await waitFor(() => {
      expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("loading-state")).not.toBeInTheDocument();
    expect(screen.queryByTestId("case-details")).not.toBeInTheDocument();
    expect(screen.queryByTestId("error-state")).not.toBeInTheDocument();
  });

  it("renders a distinct error state for database_unavailable (503)", async () => {
    render(<CaseView caseId="DSP-000050" />);
    await waitFor(() => {
      expect(screen.getByTestId("error-state")).toBeInTheDocument();
    });
    const errorState = screen.getByTestId("error-state");
    expect(errorState).toHaveAttribute("data-error-code", "database_unavailable");
    expect(errorState).toHaveAttribute("data-error-status", "503");
    expect(screen.getByText("Database Unavailable")).toBeInTheDocument();
    expect(screen.queryByTestId("case-details")).not.toBeInTheDocument();
    expect(screen.queryByTestId("empty-state")).not.toBeInTheDocument();
  });

  it("renders a distinct escalated state with human review summary", async () => {
    render(<CaseView caseId="DSP-000047" />);
    await waitFor(() => {
      expect(screen.getByTestId("case-details")).toBeInTheDocument();
    });
    const escalation = screen.getByTestId("escalation-state");
    expect(escalation).toHaveAttribute("role", "alert");
    expect(screen.getAllByText("Human decision needed").length).toBeGreaterThan(0);
    expect(screen.getByText("Full review notes")).toBeInTheDocument();
    expect(screen.queryByText("No escalation")).not.toBeInTheDocument();
  });

  it("renders a non-escalated state when not escalated", async () => {
    render(<CaseView caseId="DSP-000045" />);
    await waitFor(() => {
      expect(screen.getByTestId("case-details")).toBeInTheDocument();
    });
    expect(screen.getByTestId("escalation-state")).toBeInTheDocument();
    expect(screen.getByText(/No escalation/i)).toBeInTheDocument();
  });
});
