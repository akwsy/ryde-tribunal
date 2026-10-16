import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { JudgeRuling } from "@/components/judge-ruling";
import type { JudgeOutput, CaseResult } from "@/lib/api/types";

const baseJudge: JudgeOutput = {
  ruling_type: "refund",
  recommended_action: { description: "Test action", amount: null },
  confidence: 0.5,
  reasoning: "Test reasoning",
  evidence_references: [],
  decisive_facts: [],
  policy_references: [],
  precedent_references: [],
  precedent_binding: false,
  escalation: { escalated: false, reasons: [], human_review_summary: null },
  provider: { kind: "llm", model: "gpt-4o", policy_version: "ryde-policy-0.1.0" },
};

const baseCaseResult: CaseResult = {
  case_id: "DSP-000001",
  case_source: "live",
  ride_id: "RIDE-000001",
  category: "route_deviation",
  status: "resolved",
  synthetic: true,
  synthetic_reasoning: false,
  policy_version: "ryde-policy-0.1.0",
  created_at: "2026-09-22T00:00:00Z",
  case_facts: {},
  evidence_audit: null,
  fraud_assessment: null,
  model_proposed_ruling: null,
  reviewer_approved_ruling: null,
  advocates: {
    rider: {
      argument: "",
      claims: [],
      policy_references: [],
      invalid_citation_count: 0,
      provider: { kind: "llm" },
    },
    driver: {
      argument: "",
      claims: [],
      policy_references: [],
      invalid_citation_count: 0,
      provider: { kind: "llm" },
    },
  },
  judge: baseJudge,
  external_findings: [],
  external_unavailable: false,
  urgency: 0.5,
  case_history: [],
};

describe("Boolean rendering in measurements", () => {
  it("renders false boolean as No", () => {
    const judge: JudgeOutput = {
      ...baseJudge,
      measurements: { deviation_justified: false },
    };
    render(<JudgeRuling judge={judge} caseResult={baseCaseResult} />);
    expect(screen.getByText("No")).toBeInTheDocument();
  });

  it("renders true boolean as Yes", () => {
    const judge: JudgeOutput = {
      ...baseJudge,
      measurements: { deviation_justified: true },
    };
    render(<JudgeRuling judge={judge} caseResult={baseCaseResult} />);
    expect(screen.getByText("Yes")).toBeInTheDocument();
  });

  it("renders numeric measurement unchanged", () => {
    const judge: JudgeOutput = {
      ...baseJudge,
      measurements: { deviation_pct: 34.2 },
    };
    render(<JudgeRuling judge={judge} caseResult={baseCaseResult} />);
    expect(screen.getByText("34.2%")).toBeInTheDocument();
  });
});
