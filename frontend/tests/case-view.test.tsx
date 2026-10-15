import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { CaseView } from "@/components/case-view";
import { caseResultResolved } from "@/fixtures/case-result-resolved";
import { caseResultSynthetic } from "@/fixtures/case-result-synthetic";
import { caseResultEscalated } from "@/fixtures/case-result-escalated";
import { caseResultPendingReview } from "@/fixtures/case-result-pending-review";
import { evidenceGpsTelemetry } from "@/fixtures/evidence-gps-telemetry";
import { errorNotFound, errorDatabaseUnavailable } from "@/fixtures/errors";
import { ApiError } from "@/lib/api/client";
import type { CaseResult } from "@/lib/api/types";

const historicalCaseResult: CaseResult = {
  ...caseResultPendingReview,
  case_id: "DSP-001047",
  case_source: "archive",
  ride_id: "RIDE-001047",
  status: "resolved",
  case_facts: { subject: "Historical no-show charge dispute", filed_by: "rider" },
  model_proposed_ruling: {
    ruling_type: "refund",
    recommended_action: { description: "Refund the disputed fare.", amount: { amount_cents: 500, currency: "SGD" } },
    author_type: "model",
    decision_origin: "agent",
    author_id: null,
    credibility: "model_proposed",
    reason_code: null,
    rationale: null,
    approved_at: null,
  },
  reviewer_approved_ruling: {
    ruling_type: "refund",
    recommended_action: { description: "Refund the disputed fare.", amount: { amount_cents: 500, currency: "SGD" } },
    author_type: "human_reviewer",
    decision_origin: "human",
    author_id: null,
    credibility: "higher_than_model_proposed",
    reason_code: null,
    rationale: null,
    approved_at: "2026-08-11T09:00:00Z",
  },
};

// Mock the active client. The mock factory creates a client that returns
// fixture data based on the case ID, simulating the FixtureClient.
const mockGetDispute = vi.fn(async (caseId: string) => {
  switch (caseId) {
    case "DSP-000048":
      return { ...caseResultPendingReview, case_id: caseId, status: "queued", case_source: "live" } as CaseResult;
    case "DSP-000045":
      return caseResultResolved;
    case "DSP-000046":
      return caseResultSynthetic;
    case "DSP-000047":
      return caseResultEscalated;
    case "DSP-000049":
      return caseResultPendingReview;
    case "DSP-000051":
      return {
        ...caseResultResolved,
        case_id: caseId,
        judge: { ...caseResultResolved.judge, provider: { kind: "rules-engine", display_name: "Policy rules", model: "ryde-policy-rules-1" } },
        advocates: {
          ...caseResultResolved.advocates,
          rider: { ...caseResultResolved.advocates!.rider, provider: { kind: "rules-engine", display_name: "Policy rules", model: "ryde-policy-rules-1" } },
          driver: { ...caseResultResolved.advocates!.driver, provider: { kind: "rules-engine", display_name: "Policy rules", model: "ryde-policy-rules-1" } },
        },
      } as CaseResult;
    case "DSP-001047":
      return historicalCaseResult;
    case "DSP-000999":
      throw new ApiError(404, "not_found", "Case not found.", errorNotFound.error.details);
    case "DSP-000050":
      throw new ApiError(503, "database_unavailable", "Database unavailable.", errorDatabaseUnavailable.error.details);
    default:
      throw new ApiError(404, "not_found", "Case not found.");
  }
});
const mockGetEvidence = vi.fn(async () => evidenceGpsTelemetry);
const mockAdjudicateDispute = vi.fn(async () => ({ ...caseResultResolved, case_id: "DSP-000048" }));
const mockApproveResolution = vi.fn();
const mockOverrideResolution = vi.fn();

vi.mock("@/lib/api/fixture-client", () => ({
  getActiveClient: () => ({
    getDispute: mockGetDispute,
    adjudicateDispute: mockAdjudicateDispute,
    getEvidence: mockGetEvidence,
    approveResolution: mockApproveResolution,
    overrideResolution: mockOverrideResolution,
  }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    getClient: () => ({ getDispute: mockGetDispute }),
  };
});

describe("CaseView", () => {
  it("automatically processes a directly opened queued live case", async () => {
    mockAdjudicateDispute.mockClear();
    render(<CaseView caseId="DSP-000048" />);
    await screen.findByTestId("reviewer-actions");
    expect(mockAdjudicateDispute).toHaveBeenCalledWith("DSP-000048", "case-view-auto-DSP-000048");
  });

  it("approves the model proposal with the optional note and shows the human ruling separately", async () => {
    const modelProposal = {
      ruling_type: caseResultResolved.judge!.ruling_type,
      recommended_action: caseResultResolved.judge!.recommended_action,
      author_type: "model" as const,
      decision_origin: "agent" as const,
      author_id: "OpenAI",
      credibility: "model_proposed" as const,
      reason_code: null,
      rationale: caseResultResolved.judge!.reasoning,
      approved_at: null,
    };
    mockApproveResolution.mockResolvedValueOnce({
      ...caseResultResolved,
      model_proposed_ruling: modelProposal,
      reviewer_approved_ruling: {
        ...modelProposal,
        author_type: "human_reviewer",
        decision_origin: "human",
        credibility: "higher_than_model_proposed",
        author_id: "reviewer-default",
        rationale: "Reviewed and accepted",
        approved_at: "2026-09-25T08:00:00Z",
      },
    } satisfies CaseResult);

    render(<CaseView caseId="DSP-000045" />);
    await screen.findByTestId("reviewer-actions");
    fireEvent.change(screen.getByLabelText(/approval note/i), { target: { value: "Reviewed and accepted" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve ruling" }));

    expect(mockApproveResolution).toHaveBeenCalledWith("DSP-000045", "Reviewed and accepted");
    expect(await screen.findByTestId("reviewer-approved-ruling")).toBeInTheDocument();
    expect(screen.getByTestId("model-proposed-ruling")).toBeInTheDocument();
    expect(screen.getByTestId("judge-ruling")).toBeInTheDocument();
  });

  it("submits an override using the contract reason code, rationale, and recommended action", async () => {
    mockOverrideResolution.mockResolvedValueOnce({
      ...caseResultResolved,
      status: "overridden",
      model_proposed_ruling: {
        ruling_type: caseResultResolved.judge!.ruling_type,
        recommended_action: caseResultResolved.judge!.recommended_action,
        author_type: "model",
        decision_origin: "agent",
        author_id: "OpenAI",
        credibility: "model_proposed",
        reason_code: null,
        rationale: caseResultResolved.judge!.reasoning,
        approved_at: null,
      },
      reviewer_approved_ruling: {
        ruling_type: "no_action",
        recommended_action: { description: "No refund is due", delivery: "unspecified" },
        author_type: "human_reviewer",
        decision_origin: "human",
        author_id: "reviewer-default",
        credibility: "higher_than_model_proposed",
        reason_code: "evidence_misweighted",
        rationale: "The recorded evidence does not support a refund.",
        approved_at: "2026-09-25T08:00:00Z",
      },
    } satisfies CaseResult);

    render(<CaseView caseId="DSP-000045" />);
    await screen.findByTestId("reviewer-actions");
    fireEvent.change(screen.getByLabelText(/ruling type/i), { target: { value: "no_action" } });
    fireEvent.change(screen.getByLabelText(/reason code/i), { target: { value: "evidence_misweighted" } });
    fireEvent.change(screen.getByLabelText(/recommended action/i), { target: { value: "No refund is due" } });
    fireEvent.change(screen.getByLabelText("Rationale"), { target: { value: "The recorded evidence does not support a refund." } });
    fireEvent.click(screen.getByRole("button", { name: "Save override" }));

    await waitFor(() => expect(mockOverrideResolution).toHaveBeenCalledWith("DSP-000045", {
      ruling_type: "no_action",
      recommended_action: { description: "No refund is due", delivery: "unspecified" },
      reason_code: "evidence_misweighted",
      rationale: "The recorded evidence does not support a refund.",
    }));
    expect(await screen.findByTestId("reviewer-approved-ruling")).toBeInTheDocument();
    expect(screen.getByTestId("model-proposed-ruling")).toBeInTheDocument();
    expect(screen.getByTestId("judge-ruling")).toBeInTheDocument();
  });

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

  it("keeps raw case fields out of the reviewer summary", async () => {
    render(<CaseView caseId="DSP-000045" />);
    const summary = await screen.findByTestId("case-details");
    expect(summary).toHaveTextContent("Route Deviation");
    expect(summary).toHaveTextContent("Orchard Road, Singapore");
    expect(summary).not.toHaveTextContent(/planned_distance_km|actual_distance_km|surge_multiplier|fare_cents/);
    expect(summary).not.toHaveTextContent(/\{\s*\"/);
  });

  it("displays no synthetic badge when synthetic_reasoning is false", async () => {
    render(<CaseView caseId="DSP-000045" />);
    await waitFor(() => {
      expect(screen.getByTestId("case-details")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("synthetic-reasoning-badge")).not.toBeInTheDocument();
  });

  it("labels the rules-first path clearly", async () => {
    render(<CaseView caseId="DSP-000051" />);
    expect(await screen.findByText("Rules-based decision")).toBeInTheDocument();
    expect(screen.getAllByText("Rules-based review")).toHaveLength(2);
  });

  it("shows structured review findings and provider names without model names", async () => {
    render(<CaseView caseId="DSP-000045" />);
    await waitFor(() => {
      expect(screen.getByTestId("judge-evidence-review")).toBeInTheDocument();
      expect(screen.getByTestId("fraud-assessment")).toBeInTheDocument();
    });
    const evidenceReview = screen.getByTestId("judge-evidence-review");
    expect(evidenceReview).toHaveTextContent("Needs attention");
    expect(evidenceReview).toHaveTextContent("Conflicting with the trip record");
    fireEvent.click(within(evidenceReview).getByText("View evidence check details"));
    expect(within(evidenceReview).getByText("Checked by OpenAI.")).toBeInTheDocument();
    expect(within(screen.getByTestId("fraud-assessment")).getByText("Provider: OpenAI")).toBeInTheDocument();
    expect(evidenceReview).toHaveTextContent(/Driver’s case · contradicted/i);
    expect(evidenceReview).toHaveTextContent(/92\.0% confidence/);
    expect(screen.getAllByText(/The recorded GPS distance is 18.4 km/)).toHaveLength(1);
    expect(screen.getByText("65.0%")).toBeInTheDocument();
    expect(screen.getByText("80.0%")).toBeInTheDocument();
    expect(screen.getByText(/claim evidence mismatch/i)).toBeInTheDocument();
    expect(screen.queryByText(/fixture-model|gpt-4o/)).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "View evidence" })[0]);
    expect(await screen.findByTestId("evidence-detail-EV-000789")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
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

  it("renders human review without inventing advocates or a judge ruling", async () => {
    render(<CaseView caseId="DSP-000049" />);
    expect(await screen.findByTestId("pending-review")).toBeInTheDocument();
    expect(screen.getByText(/reviewer must assess the reported lost item/i)).toBeInTheDocument();
    expect(screen.queryByTestId("advocate-panel-rider")).not.toBeInTheDocument();
    expect(screen.queryByTestId("judge-ruling")).not.toBeInTheDocument();
    expect(screen.queryByTestId("evidence-audit")).not.toBeInTheDocument();
    expect(screen.queryByTestId("fraud-assessment")).not.toBeInTheDocument();
  });

  it("renders historical rulings as read-only and hides reviewer actions", async () => {
    render(<CaseView caseId="DSP-001047" />);

    expect(await screen.findByTestId("historical-read-only")).toBeInTheDocument();
    expect(screen.getByTestId("case-id")).toHaveTextContent("DSP-001047");
    expect(screen.getByTestId("model-proposed-ruling")).toBeInTheDocument();
    expect(screen.getByTestId("reviewer-approved-ruling")).toBeInTheDocument();
    expect(screen.queryByTestId("reviewer-actions")).not.toBeInTheDocument();
    expect(screen.queryByTestId("judge-ruling")).not.toBeInTheDocument();
    expect(screen.queryByTestId("advocate-panel-rider")).not.toBeInTheDocument();
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
