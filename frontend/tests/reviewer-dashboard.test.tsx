import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReviewerDashboard } from "@/components/reviewer-dashboard";
import { presetRange, singaporeToday } from "@/lib/dashboard-dates";

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

  it("shows provider as the provider value and cases as not urgent", async () => {
    render(<ReviewerDashboard />);
    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    fireEvent.change(screen.getByLabelText("Custom range start"), { target: { value: "2026-09-22" } });
    fireEvent.change(screen.getByLabelText("Custom range end"), { target: { value: "2026-09-23" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply range" }));
    await waitFor(() => expect(screen.getByText("DSP-000045")).toBeInTheDocument());
    expect(screen.getAllByText("Not urgent").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Gemini").length).toBeGreaterThan(0);
    expect(screen.queryByText(/gemini.*flash/i)).not.toBeInTheDocument();
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
});
