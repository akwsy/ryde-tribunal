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

    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);

    await waitFor(() => {
      expect(screen.getByTestId("evidence-detail-EV-000789")).toBeInTheDocument();
    });

    expect(screen.getAllByText("EV-000789").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("GPS Telemetry")).toBeInTheDocument();
    expect(screen.getByText("Provenance")).toBeInTheDocument();
    expect(screen.getByText("Payload")).toBeInTheDocument();
  });

  it("renders verification status and uncertainty percentage", async () => {
    const user = userEvent.setup();
    render(<EvidenceControl evidenceId="EV-000789" caseId="DSP-000045" />);

    await user.click(screen.getByRole("button"));

    await waitFor(() => {
      const badge = screen.getByTestId("verification-badge");
      expect(badge).toHaveTextContent("Verified");
      expect(badge).toHaveTextContent("2.5%");
    });
  });

  it("renders uncertainty N/A when uncertainty_pct is absent", async () => {
    const user = userEvent.setup();
    render(<EvidenceControl evidenceId="EV-000790" caseId="DSP-000045" />);

    await user.click(screen.getByRole("button"));

    await waitFor(() => {
      const badge = screen.getByTestId("verification-badge");
      expect(badge).toHaveTextContent("Verified");
      expect(badge).toHaveTextContent("uncertainty N/A");
    });
  });

  it("is keyboard accessible", async () => {
    const user = userEvent.setup();
    render(<EvidenceControl evidenceId="EV-000789" caseId="DSP-000045" />);

    const button = screen.getByRole("button");
    button.focus();
    expect(button).toHaveFocus();

    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(screen.getByTestId("evidence-detail-EV-000789")).toBeInTheDocument();
    });
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
    expect(screen.getByTestId("verification-badge")).toHaveTextContent("uncertainty N/A");
  });

  it("renders uncertainty N/A when undefined", () => {
    render(<VerificationBadge status="disputed" />);
    const badge = screen.getByTestId("verification-badge");
    expect(badge).toHaveTextContent("Disputed");
    expect(badge).toHaveTextContent("uncertainty N/A");
  });

  it("renders a safe fallback for unknown status", () => {
    render(<VerificationBadge status="bogus" uncertaintyPct={5} />);
    expect(screen.getByTestId("verification-badge")).toHaveTextContent("Unknown status: bogus");
  });
});
