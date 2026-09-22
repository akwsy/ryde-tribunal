import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AdvocatePanel } from "@/components/advocate-panel";
import type { AdvocateOutput } from "@/lib/api/types";

const baseAdvocate: AdvocateOutput = {
  argument: "Test argument",
  claims: [
    {
      text: "Test claim",
      citations: [],
    },
  ],
  policy_references: [],
  invalid_citation_count: 0,
  provider: { kind: "llm", model: "gpt-4o", policy_version: "ryde-policy-0.1.0" },
};

function makeAdvocateWithCitation(valid: boolean | undefined): AdvocateOutput {
  return {
    ...baseAdvocate,
    claims: [
      {
        text: "Claim with citation",
        citations: [
          {
            evidence_id: "EV-000001",
            field_path: "test.field",
            observed_value: "x",
            supports: "claim-1",
            valid: valid as boolean,
          },
        ],
      },
    ],
  };
}

describe("Citation valid rendering", () => {
  it("renders (valid) in green when valid is true", () => {
    render(
      <AdvocatePanel
        role="rider"
        advocate={makeAdvocateWithCitation(true)}
        caseId="DSP-000001"
        syntheticReasoning={false}
        side="left"
      />
    );
    expect(screen.getByText("(valid)")).toBeInTheDocument();
    expect(screen.getByText("(valid)")).toHaveClass("text-green-600");
  });

  it("renders (invalid) in red when valid is false", () => {
    render(
      <AdvocatePanel
        role="rider"
        advocate={makeAdvocateWithCitation(false)}
        caseId="DSP-000001"
        syntheticReasoning={false}
        side="left"
      />
    );
    expect(screen.getByText("(invalid)")).toBeInTheDocument();
    expect(screen.getByText("(invalid)")).toHaveClass("text-red-600");
  });

  it("renders (unknown) in amber when valid is absent", () => {
    const advocate = makeAdvocateWithCitation(undefined);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (advocate.claims[0].citations[0] as any).valid = undefined;
    render(
      <AdvocatePanel
        role="rider"
        advocate={advocate}
        caseId="DSP-000001"
        syntheticReasoning={false}
        side="left"
      />
    );
    expect(screen.getByText("(unknown)")).toBeInTheDocument();
    expect(screen.getByText("(unknown)")).toHaveClass("text-amber-600");
  });
});
