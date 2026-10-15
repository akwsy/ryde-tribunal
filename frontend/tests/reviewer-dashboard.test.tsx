import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReviewerDashboard } from "@/components/reviewer-dashboard";
import { presetRange, singaporeToday } from "@/lib/dashboard-dates";
import { FixtureClient } from "@/lib/api/fixture-client";
import { caseSummaryPage } from "@/fixtures/case-summary-page";

describe("reviewer dashboard", () => {
  it("defaults to today and offers only the approved pie dimensions", async () => {
    const today = singaporeToday();
    const week = presetRange("week");
    render(<ReviewerDashboard />);

    await waitFor(() => expect(screen.getByText("Cases filed over time")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Today" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(`${today} to ${today} (Asia/Singapore)`)).toBeInTheDocument();
    expect(screen.getByText("Cases filed")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "This week" }));
    await waitFor(() => expect(screen.getByText("Cases filed over time")).toBeInTheDocument());
    expect(screen.getByText("Cases filed")).toBeInTheDocument();
    expect(screen.getByText(`${week.from} to ${week.to} (Asia/Singapore)`)).toBeInTheDocument();

    const grouping = screen.getByLabelText("Pie chart grouping") as HTMLSelectElement;
    expect(Array.from(grouping.options).map((option) => option.value)).toEqual([
      "category", "status", "filed_by", "provider",
    ]);
    expect(grouping.value).toBe("category");
  });

  it("shows the result and review status in the all cases list", async () => {
    render(<ReviewerDashboard />);
    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    fireEvent.change(screen.getByLabelText("Custom range start"), { target: { value: "2026-09-22" } });
    fireEvent.change(screen.getByLabelText("Custom range end"), { target: { value: "2026-09-23" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply range" }));
    await waitFor(() => expect(screen.getByText("DSP-000045")).toBeInTheDocument());
    expect(screen.getAllByText("Refund").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Resolved").length).toBeGreaterThan(0);
  });

  it("shows historical and live cases in the same list without archive-specific labels", async () => {
    render(<ReviewerDashboard />);
    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    fireEvent.change(screen.getByLabelText("Custom range start"), { target: { value: "2026-08-01" } });
    fireEvent.change(screen.getByLabelText("Custom range end"), { target: { value: "2026-09-30" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply range" }));

    const historicalCase = await screen.findByRole("link", { name: "DSP-001047" });
    expect(historicalCase).toHaveAttribute("href", "/cases/DSP-001047");
    expect(screen.queryByRole("link", { name: "All archived cases" })).not.toBeInTheDocument();
    expect(screen.queryByText(/· archive$/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "DSP-000045" })).toHaveAttribute("href", "/cases/DSP-000045");
    expect(screen.getByText(/RIDE-001047/)).toBeInTheDocument();
    expect(screen.queryByText(/RIDE-ARCH-/)).not.toBeInTheDocument();
  });

  it("keeps old filing dates in the all cases list when charts remain on Today", async () => {
    render(<ReviewerDashboard />);
    expect(screen.getByRole("button", { name: "Today" })).toHaveAttribute("aria-pressed", "true");
    await screen.findByRole("heading", { name: "All cases" });
    fireEvent.change(screen.getByRole("searchbox", { name: "Search cases" }), { target: { value: "DSP-001047" } });
    expect(await screen.findByRole("link", { name: "DSP-001047" })).toHaveAttribute("href", "/cases/DSP-001047");
  });

  it("shows the empty-period state with an accessible demonstration button and updates the date range on click", async () => {
    const user = userEvent.setup();
    render(<ReviewerDashboard />);

    // Today (14 Oct 2026 in fixture time) has zero filed cases.
    const demoButton = await screen.findByTestId("demo-period-button");
    expect(demoButton).toBeVisible();
    expect(demoButton.tagName).toBe("BUTTON");
    expect(demoButton).toHaveAttribute(
      "aria-label",
      "Open the synthetic demonstration period (12 to 13 October 2026)",
    );

    // The Today default is still selected.
    expect(screen.getByRole("button", { name: "Today" })).toHaveAttribute("aria-pressed", "true");

    await user.click(demoButton);

    // The period switches to Custom and the range text shows the demonstration dates.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Custom" })).toHaveAttribute("aria-pressed", "true"),
    );
    expect(screen.getByText(/2026-10-12 to 2026-10-13/)).toBeInTheDocument();

    // Custom-range inputs reflect the selected demonstration dates.
    expect(screen.getByLabelText("Custom range start")).toHaveValue("2026-10-12");
    expect(screen.getByLabelText("Custom range end")).toHaveValue("2026-10-13");
  });

  it("automatically starts queued live cases and shows an under-review queue", async () => {
    const queued = {
      ...caseSummaryPage.items[0],
      case_id: "DSP-009955",
      status: "queued" as const,
      confidence: null,
      ruling_type: null,
    };
    let listCalls = 0;
    let finishReview!: () => void;
    const reviewGate = new Promise<void>((resolve) => { finishReview = resolve; });
    const listSpy = vi.spyOn(FixtureClient.prototype, "listDisputes").mockImplementation(async () => {
      listCalls += 1;
      return {
        items: [listCalls === 1 ? queued : { ...queued, status: "resolved" as const, ruling_type: "no_action" as const }],
        next_cursor: null,
      };
    });
    const adjudicateSpy = vi.spyOn(FixtureClient.prototype, "adjudicateDispute").mockImplementation(async () => {
      await reviewGate;
      const { caseResultResolved } = await import("@/fixtures/case-result-resolved");
      return { ...caseResultResolved, case_id: queued.case_id };
    });

    render(<ReviewerDashboard />);
    await waitFor(() => expect(adjudicateSpy).toHaveBeenCalledWith(
      "DSP-009955", "dashboard-auto-DSP-009955",
    ));
    expect(screen.getByRole("button", { name: /Under review/ })).toHaveTextContent("1");
    expect(screen.getByRole("status")).toHaveTextContent("Agents are checking case evidence");

    finishReview();
    await waitFor(() => expect(listCalls).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.getByRole("button", { name: /Decision decided/ })).toHaveTextContent("1"));
    listSpy.mockRestore();
    adjudicateSpy.mockRestore();
  });
});
