import type { CaseResult } from "@/lib/api/types";
import { caseResultResolved } from "./case-result-resolved";

/**
 * FIXTURE — not production data. All data is synthetic.
 *
 * Same case as resolved, but synthetic_reasoning: true to test the badge.
 * All providers are deterministic-mock.
 */
export const caseResultSynthetic: CaseResult = {
  ...caseResultResolved,
  case_id: "DSP-000046",
  synthetic_reasoning: true,
  advocates: {
    rider: {
      ...caseResultResolved.advocates.rider,
      provider: {
        kind: "deterministic-mock" as const,
        model: "scripted-fallback-v1",
        policy_version: "ryde-policy-0.1.0",
      },
    },
    driver: {
      ...caseResultResolved.advocates.driver,
      provider: {
        kind: "deterministic-mock" as const,
        model: "scripted-fallback-v1",
        policy_version: "ryde-policy-0.1.0",
      },
    },
  },
  judge: {
    ...caseResultResolved.judge,
    provider: {
      kind: "deterministic-mock" as const,
      model: "scripted-fallback-v1",
      policy_version: "ryde-policy-0.1.0",
    },
    reasoning:
      "The actual distance exceeds the planned distance by 34.2%, above the 15% tolerance in RP-ROUTE-002. No rider-requested change or evidenced road closure was found. The rider is entitled to a refund of the excess fare under RP-ROUTE-003 and RP-FARE-001.",
    confidence: 0.842,
  },
  case_history: [
    ...caseResultResolved.case_history.map((e) => ({
      ...e,
      at: e.at.replace("07:08", "07:10").replace("07:09", "07:11"),
    })),
  ],
  created_at: "2026-09-22T07:10:00Z",
};
