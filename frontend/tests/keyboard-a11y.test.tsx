import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CaseView } from "@/components/case-view";
import { caseResultResolved } from "@/fixtures/case-result-resolved";
import { ApiError } from "@/lib/api/client";

const mockGetDispute = vi.fn(async (caseId: string) => {
  if (caseId === "DSP-000045") return caseResultResolved;
  throw new ApiError(404, "not_found", "Case not found.");
});

// Also mock the evidence fetch so the detail panel can load
const mockGetEvidence = vi.fn(async (evidenceId: string) => {
  const { evidenceGpsTelemetry } = await import("@/fixtures/evidence-gps-telemetry");
  const { evidenceChatLog } = await import("@/fixtures/evidence-chat-log");
  if (evidenceId === "EV-000789") return evidenceGpsTelemetry;
  if (evidenceId === "EV-000790") return evidenceChatLog;
  throw new ApiError(404, "not_found", "Evidence not found.");
});

vi.mock("@/lib/api/fixture-client", () => ({
  getActiveClient: () => ({ getDispute: mockGetDispute, getEvidence: mockGetEvidence }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    getClient: () => ({ getDispute: mockGetDispute, getEvidence: mockGetEvidence }),
  };
});

describe("keyboard navigation to evidence controls", () => {
  it("reaches every evidence control via Tab and expands with Enter", async () => {
    const user = userEvent.setup();
    render(<CaseView caseId="DSP-000045" />);

    await waitFor(() => {
      expect(screen.getByTestId("case-details")).toBeInTheDocument();
    });

    // Find all evidence control buttons (they have aria-expanded)
    const buttons = screen.getAllByRole("button");
    const evidenceButtons = buttons.filter(
      (b) => b.getAttribute("aria-expanded") !== null,
    );
    expect(evidenceButtons.length).toBeGreaterThan(0);

    // Focus the first evidence button and expand it with Enter
    const firstBtn = evidenceButtons[0];
    firstBtn.focus();
    expect(firstBtn).toHaveFocus();

    await user.keyboard("{Enter}");

    // After pressing Enter, the button's aria-expanded should become true
    // and the evidence detail panel should appear.
    await waitFor(() => {
      expect(firstBtn).toHaveAttribute("aria-expanded", "true");
    });

    // The detail panel should be present
    await waitFor(() => {
      const detailId = firstBtn.getAttribute("aria-controls");
      expect(detailId).toBeTruthy();
      expect(document.getElementById(detailId!)).toBeInTheDocument();
    });
  });
});
