import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { WorkspaceHeader } from "@/components/workspace-header";
import { AgentTimeline } from "@/components/agent-timeline";
import { caseResultResolved } from "@/fixtures/case-result-resolved";

describe("submission honesty", () => {
 it("labels recorded examples separately from provider names", () => {
   render(<WorkspaceHeader />);
   expect(screen.getByRole("status")).toHaveTextContent("do not demonstrate live AI calls");
 });
 it("never fabricates an agent trace for old examples", () => {
   render(<AgentTimeline result={caseResultResolved} />);
   expect(screen.getByText("No agent trace was recorded for this historical example.")).toBeInTheDocument();
 });
});
