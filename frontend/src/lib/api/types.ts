import type { components } from "./generated";

/** Type aliases for every schema in the contract. Every component consumes these — never hand-written. */

export type Money = components["schemas"]["Money"];
export type Category = components["schemas"]["Category"];
export type CaseStatus = components["schemas"]["CaseStatus"];
export type RulingType = components["schemas"]["RulingType"];
export type ReasonCode = components["schemas"]["ReasonCode"];
export type VerificationStatus = components["schemas"]["VerificationStatus"];
export type ProviderKind = components["schemas"]["ProviderKind"];
export type Provider = components["schemas"]["Provider"];
export type Verification = components["schemas"]["Verification"];
export type Citation = components["schemas"]["Citation"];
export type Claim = components["schemas"]["Claim"];
export type RejectedEvidence = components["schemas"]["RejectedEvidence"];
export type AdvocateOutput = components["schemas"]["AdvocateOutput"];
export type Advocates = components["schemas"]["Advocates"];
export type RecommendedAction = components["schemas"]["RecommendedAction"];
export type EscalationReason = components["schemas"]["EscalationReason"];
export type Escalation = components["schemas"]["Escalation"];
export type JudgeOutput = components["schemas"]["JudgeOutput"];
export type ExternalFinding = components["schemas"]["ExternalFinding"];
export type HistoryEvent = components["schemas"]["HistoryEvent"];
export type CaseResult = components["schemas"]["CaseResult"];
export type CaseSummary = components["schemas"]["CaseSummary"];
export type CaseSummaryPage = components["schemas"]["CaseSummaryPage"];
export type Evidence = components["schemas"]["Evidence"];
export type FileDisputeRequest = components["schemas"]["FileDisputeRequest"];
export type FileDisputeResponse = components["schemas"]["FileDisputeResponse"];
export type OverrideRequest = components["schemas"]["OverrideRequest"];
export type MetricsOverview = components["schemas"]["MetricsOverview"];
export type MetricsTimeseries = components["schemas"]["MetricsTimeseries"];
export type PolicyDocument = components["schemas"]["PolicyDocument"];
export type Health = components["schemas"]["Health"];
export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];
