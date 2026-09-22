import type {
  CaseResult,
  CaseSummaryPage,
  Evidence,
  ErrorEnvelope,
  FileDisputeRequest,
  FileDisputeResponse,
  Health,
  HistoryEvent,
  MetricsOverview,
  MetricsTimeseries,
  OverrideRequest,
  PolicyDocument,
} from "./types";
import { ApiError, type ListDisputesParams } from "./client";

import { caseResultResolved } from "@/fixtures/case-result-resolved";
import { caseResultSynthetic } from "@/fixtures/case-result-synthetic";
import { caseResultEscalated } from "@/fixtures/case-result-escalated";
import { caseResultNoShow } from "@/fixtures/case-result-no-show";
import { evidenceGpsTelemetry } from "@/fixtures/evidence-gps-telemetry";
import { evidenceChatLog } from "@/fixtures/evidence-chat-log";
import { evidenceFareUnverified } from "@/fixtures/evidence-fare-unverified";
import { caseSummaryPage } from "@/fixtures/case-summary-page";
import { metricsOverview } from "@/fixtures/metrics-overview";
import { metricsTimeseries } from "@/fixtures/metrics-timeseries";
import { policyDocument } from "@/fixtures/policy-document";
import { healthOk } from "@/fixtures/health";
import { errorNotFound, errorDatabaseUnavailable, errorInternal } from "@/fixtures/errors";

/**
 * Fixture client — a drop-in replacement for TribunalClient when
 * NEXT_PUBLIC_API_BASE_URL is not set.
 *
 * FIXTURE — not production data. All data is synthetic.
 */
export class FixtureClient {
  readonly isFixture = true as const;

  async getDispute(caseId: string): Promise<CaseResult> {
    await delay();
    switch (caseId) {
      case "DSP-000045":
        return caseResultResolved;
      case "DSP-000046":
        return caseResultSynthetic;
      case "DSP-000047":
        return caseResultEscalated;
      case "DSP-000048":
        return caseResultNoShow;
      case "DSP-000999":
        throw toApiError(404, errorNotFound);
      case "DSP-000050":
        throw toApiError(503, errorDatabaseUnavailable);
      default:
        throw toApiError(404, errorNotFound);
    }
  }

  async listDisputes(_params?: ListDisputesParams): Promise<CaseSummaryPage> {
    await delay();
    return caseSummaryPage;
  }

  async adjudicateDispute(caseId: string, _idempotencyKey?: string): Promise<CaseResult> {
    await delay();
    return this.getDispute(caseId);
  }

  async fileDispute(_body: FileDisputeRequest, _idempotencyKey?: string): Promise<FileDisputeResponse> {
    await delay();
    return { case_id: "DSP-000049", status: "queued" };
  }

  async approveResolution(caseId: string, _note?: string): Promise<CaseResult> {
    await delay();
    return this.getDispute(caseId);
  }

  async overrideResolution(caseId: string, _body: OverrideRequest): Promise<CaseResult> {
    await delay();
    return this.getDispute(caseId);
  }

  async getCaseHistory(_caseId: string): Promise<HistoryEvent[]> {
    await delay();
    return caseResultResolved.case_history;
  }

  async getEvidence(evidenceId: string): Promise<Evidence> {
    await delay();
    switch (evidenceId) {
      case "EV-000789":
        return evidenceGpsTelemetry;
      case "EV-000790":
        return evidenceChatLog;
      case "EV-000792":
        return evidenceFareUnverified;
      default:
        throw toApiError(404, errorNotFound);
    }
  }

  async getMetricsOverview(_tz?: string): Promise<MetricsOverview> {
    await delay();
    return metricsOverview;
  }

  async getMetricsTimeseries(_params?: {
    granularity?: "day" | "week";
    from?: string;
    to?: string;
  }): Promise<MetricsTimeseries> {
    await delay();
    return metricsTimeseries;
  }

  async getPolicy(_version: string): Promise<PolicyDocument> {
    await delay();
    return policyDocument;
  }

  async getHealth(): Promise<Health> {
    await delay();
    return healthOk;
  }

  // Test helper: simulate a 500 error
  async getDispute500(_caseId: string): Promise<CaseResult> {
    await delay();
    throw toApiError(500, errorInternal);
  }
}

function delay(ms = 50): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function toApiError(status: number, envelope: ErrorEnvelope): ApiError {
  return new ApiError(
    status,
    envelope.error.code,
    envelope.error.message,
    envelope.error.details,
  );
}

// ── Factory ───────────────────────────────────────────────────────────────────
let _fixtureClient: FixtureClient | null = null;

export function getFixtureClient(): FixtureClient {
  if (!_fixtureClient) {
    _fixtureClient = new FixtureClient();
  }
  return _fixtureClient;
}

/**
 * Returns the appropriate client based on whether NEXT_PUBLIC_API_BASE_URL is set.
 * When unset, returns a FixtureClient (visibly labelled). When set, returns a
 * TribunalClient pointed at the live API.
 */
export function getActiveClient(): TribunalClient | FixtureClient {
  const baseURL =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL
      ? process.env.NEXT_PUBLIC_API_BASE_URL
      : "";
  if (!baseURL) {
    return getFixtureClient();
  }
  // Import here to avoid circular dep in the singleton above
  const { getClient } = require("./client") as typeof import("./client");
  return getClient();
}

// Re-export type for the union
import type { TribunalClient } from "./client";
