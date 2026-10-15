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
  it("marks a valid citation as checked", () => {
    render(
      <AdvocatePanel
        role="rider"
        advocate={makeAdvocateWithCitation(true)}
        caseId="DSP-000001"
        syntheticReasoning={false}
        side="left"
      />
    );
    expect(screen.getByText("Source checked")).toHaveClass("valid");
  });

  it("marks an invalid citation for review", () => {
    render(
      <AdvocatePanel
        role="rider"
        advocate={makeAdvocateWithCitation(false)}
        caseId="DSP-000001"
        syntheticReasoning={false}
        side="left"
      />
    );
    expect(screen.getByText("Citation needs review")).toHaveClass("invalid");
  });

  it("treats an absent validation result as requiring review", () => {
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
    expect(screen.getByText("Citation needs review")).toHaveClass("invalid");
  });
});
