import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EvidenceControl, VerificationBadge } from "@/components/evidence-control";
import { evidenceGpsTelemetry } from "@/fixtures/evidence-gps-telemetry";
import { evidenceChatLog } from "@/fixtures/evidence-chat-log";
import { ApiError } from "@/lib/api/client";

const mockGetEvidence = vi.fn(async (evidenceId: string) => {
  switch (evidenceId) {
    case "EV-000789":
      return evidenceGpsTelemetry;
    case "EV-000790":
      return evidenceChatLog;
    default:
      throw new ApiError(404, "not_found", "Evidence not found.");
  }
});

vi.mock("@/lib/api/fixture-client", () => ({
  getActiveClient: () => ({ getEvidence: mockGetEvidence }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    getClient: () => ({ getEvidence: mockGetEvidence }),
  };
});

describe("EvidenceControl", () => {
  it("renders a clickable control that reveals the evidence record", async () => {
    const user = userEvent.setup();
    render(<EvidenceControl evidenceId="EV-000789" caseId="DSP-000045" />);

    const button = screen.getByRole("button", { name: "View evidence" });
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);

    await waitFor(() => {
      expect(screen.getByTestId("evidence-detail-EV-000789")).toBeInTheDocument();
    });

    expect(screen.getAllByText("EV-000789").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("GPS Telemetry").length).toBeGreaterThan(0);
    expect(screen.getByText("Technical details")).toBeInTheDocument();
  });

  it("renders verification status and uncertainty percentage", async () => {
    const user = userEvent.setup();
    render(<EvidenceControl evidenceId="EV-000789" caseId="DSP-000045" />);

    await user.click(screen.getByRole("button", { name: "View evidence" }));

    await waitFor(() => {
      const badge = screen.getByTestId("verification-badge");
      expect(badge).toHaveTextContent("Verified");
      expect(badge).toHaveTextContent("2.5%");
    });
  });

  it("renders uncertainty N/A when uncertainty_pct is absent", async () => {
    const user = userEvent.setup();
    render(<EvidenceControl evidenceId="EV-000790" caseId="DSP-000045" />);

    await user.click(screen.getByRole("button", { name: "View evidence" }));

    await waitFor(() => {
      const badge = screen.getByTestId("verification-badge");
      expect(badge).toHaveTextContent("Verified");
      expect(badge).not.toHaveTextContent("uncertainty");
    });
  });

  it("is keyboard accessible", async () => {
    const user = userEvent.setup();
    render(<EvidenceControl evidenceId="EV-000789" caseId="DSP-000045" />);

    const button = screen.getByRole("button", { name: "View evidence" });
    button.focus();
    expect(button).toHaveFocus();

    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(screen.getByTestId("evidence-detail-EV-000789")).toBeInTheDocument();
    });
  });

  it("closes with Escape, returns focus, and labels the cited fact in plain language", async () => {
    const user = userEvent.setup();
    render(<EvidenceControl evidenceId="EV-000789" caseId="DSP-000045" title="Recorded distance" citedField="actual_distance_km" observedValue={18.4} summary="18.4 km travelled" />);
    const opener = screen.getByRole("button", { name: "View evidence" });
    await user.click(opener);
    expect(await screen.findByText("Used for this point")).toBeInTheDocument();
    expect(screen.getByText("18.4 km")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("keeps keyboard-moved evidence panels inside the viewport", async () => {
    const user = userEvent.setup();
    const originalWidth = window.innerWidth;
    const originalHeight = window.innerHeight;
    window.innerWidth = 1000;
    window.innerHeight = 1200;
    render(<EvidenceControl evidenceId="EV-000789" caseId="DSP-000045" />);
    await user.click(screen.getByRole("button", { name: "View evidence" }));

    const dialog = await screen.findByRole("dialog");
    const moveHandle = screen.getByLabelText("Move evidence panel with arrow keys");
    moveHandle.focus();
    for (let index = 0; index < 40; index += 1) await user.keyboard("{ArrowRight}{ArrowDown}");

    expect(dialog.style.left).toBe("264px");
    expect(dialog.style.top).toBe("364px");
    window.innerWidth = originalWidth;
    window.innerHeight = originalHeight;
  });

  it("opens as an accessible modal dialog with focus management and Escape-to-close", async () => {
    const user = userEvent.setup();
    render(<EvidenceControl evidenceId="EV-000789" caseId="DSP-000045" />);
    const opener = screen.getByRole("button", { name: "View evidence" });
    expect(opener).toHaveAttribute("aria-haspopup", "dialog");

    await user.click(opener);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(opener).toHaveAttribute("aria-expanded", "true");

    // Wait for evidence to load.
    await waitFor(() => expect(screen.getByText("Technical details")).toBeInTheDocument());

    // The close button receives initial focus.
    const closeBtn = screen.getByRole("button", { name: /close evidence/i });
    expect(closeBtn).toHaveFocus();

    // Escape closes the dialog and returns focus to the opener.
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(opener).toHaveFocus());
    expect(opener).toHaveAttribute("aria-expanded", "false");
  });

  it("shows clear metadata labels with units and preserves the exact evidence record", async () => {
    const user = userEvent.setup();
    render(<EvidenceControl evidenceId="EV-000789" caseId="DSP-000045" />);
    await user.click(screen.getByRole("button", { name: "View evidence" }));

    await waitFor(() => {
      expect(screen.getByTestId("evidence-detail-EV-000789")).toBeInTheDocument();
    });

    // Metadata uses clear, unit-bearing labels.
    expect(screen.getByText("Recorded at")).toBeInTheDocument();
    expect(screen.getByText("Evidence source")).toBeInTheDocument();
    expect(screen.getByText("Visible to")).toBeInTheDocument();
    expect(screen.getByText("Evidence ID")).toBeInTheDocument();

    // The exact evidence record values are preserved.
    expect(screen.getAllByText("EV-000789").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("system record")).toBeInTheDocument();
    expect(screen.getByText("both")).toBeInTheDocument();

    // Verification status is preserved.
    const badge = screen.getByTestId("verification-badge");
    expect(badge).toHaveTextContent("Verified");
    expect(badge).toHaveTextContent("2.5%");
  });

  it("renders long text without overflow on a 390-pixel screen", async () => {
    const user = userEvent.setup();
    const originalWidth = window.innerWidth;
    window.innerWidth = 390;
    window.dispatchEvent(new Event("resize"));

    const longSummary =
      "This GPS telemetry record contains a very long route description that spans multiple " +
      "paragraphs and includes extensive detail about every waypoint, turn, and traffic condition " +
      "encountered during the trip from Orchard Road to Changi Airport Terminal 3 via the ECP highway.";
    render(
      <EvidenceControl
        evidenceId="EV-000789"
        caseId="DSP-000045"
        title="Recorded GPS route with an unusually long evidence title that may overflow narrow viewports"
        summary={longSummary}
        citedField="actual_distance_km"
        observedValue={18.4}
      />,
    );

    await user.click(screen.getByRole("button", { name: "View evidence" }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();

    // Long title renders without truncating content (in both the card and dialog).
    const longTitle = "Recorded GPS route with an unusually long evidence title that may overflow narrow viewports";
    const titleEls = screen.getAllByText(longTitle);
    expect(titleEls.length).toBeGreaterThanOrEqual(1);

    // Long summary text is fully visible in the card.
    expect(screen.getByText(longSummary)).toBeInTheDocument();

    // The observed value retains its unit.
    expect(screen.getByText("18.4 km")).toBeInTheDocument();

    // Technical details <pre> elements are present and scrollable.
    const details = screen.getByText("Technical details");
    await user.click(details);
    const pres = dialog.querySelectorAll("pre");
    expect(pres.length).toBeGreaterThan(0);

    window.innerWidth = originalWidth;
    window.dispatchEvent(new Event("resize"));
  });
});

describe("VerificationBadge", () => {
  it("renders verified status with uncertainty", () => {
    render(<VerificationBadge status="verified" uncertaintyPct={2.5} />);
    const badge = screen.getByTestId("verification-badge");
    expect(badge).toHaveTextContent("Verified");
    expect(badge).toHaveTextContent("2.5%");
  });

  it("renders unverified status with uncertainty", () => {
    render(<VerificationBadge status="unverified" uncertaintyPct={15} />);
    const badge = screen.getByTestId("verification-badge");
    expect(badge).toHaveTextContent("Unverified");
    expect(badge).toHaveTextContent("15%");
  });

  it("renders uncertainty N/A when null", () => {
    render(<VerificationBadge status="verified" uncertaintyPct={null} />);
    expect(screen.getByTestId("verification-badge")).not.toHaveTextContent("uncertainty");
  });

  it("renders uncertainty N/A when undefined", () => {
    render(<VerificationBadge status="disputed" />);
    const badge = screen.getByTestId("verification-badge");
    expect(badge).toHaveTextContent("Disputed");
    expect(badge).not.toHaveTextContent("uncertainty");
  });

  it("renders a safe fallback for unknown status", () => {
    render(<VerificationBadge status="bogus" uncertaintyPct={5} />);
    expect(screen.getByTestId("verification-badge")).toHaveTextContent("Unknown status: bogus");
  });
});
