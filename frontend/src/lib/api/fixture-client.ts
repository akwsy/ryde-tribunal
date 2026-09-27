import type {
  CaseResult,
  CaseSummaryPage,
  CaseSummary,
  ArchiveDisputePage,
  Evidence,
  ErrorEnvelope,
  FileDisputeRequest,
  FileDisputeResponse,
  Health,
  HistoryEvent,
  ImportResult,
  MetricsBreakdown,
  MetricsOverview,
  MetricsTimeseries,
  OverrideRequest,
  PolicyDocument,
  TripSearchPage,
} from "./types";
import { ApiError, type ListDisputesParams } from "./client";

import { caseResultResolved } from "@/fixtures/case-result-resolved";
import { caseResultSynthetic } from "@/fixtures/case-result-synthetic";
import { caseResultEscalated } from "@/fixtures/case-result-escalated";
import { caseResultNoShow } from "@/fixtures/case-result-no-show";
import { caseResultPendingReview } from "@/fixtures/case-result-pending-review";
import { evidenceGpsTelemetry } from "@/fixtures/evidence-gps-telemetry";
import { evidenceChatLog } from "@/fixtures/evidence-chat-log";
import { evidenceFareUnverified } from "@/fixtures/evidence-fare-unverified";
import { caseSummaryPage } from "@/fixtures/case-summary-page";
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
      case "DSP-000049":
        return caseResultPendingReview;
      case "DSP-000999":
        throw toApiError(404, errorNotFound);
      case "DSP-000050":
        throw toApiError(503, errorDatabaseUnavailable);
    }
    const historical = (await this.listArchivedDisputes()).items.find(
      (item) => item.archive_case_id === caseId,
    );
    if (historical) return archiveCaseResult(historical);
    throw toApiError(404, errorNotFound);
  }

  async listDisputes(params?: ListDisputesParams): Promise<CaseSummaryPage> {
    await delay();
    const archived = archiveSummaries(await this.listArchivedDisputes());
    let items = [...caseSummaryPage.items, ...archived].filter((item) =>
      withinDateRange(item.created_at, params?.from, params?.to) &&
      (!params?.status || item.status === params.status) &&
      (!params?.category || item.category === params.category) &&
      (params?.needs_review === undefined || item.needs_review === params.needs_review) &&
      (params?.urgency_min === undefined || item.urgency >= params.urgency_min),
    );
    if (params?.sort) {
      const descending = params.sort.startsWith("-");
      const key = params.sort.replace(/^-/, "");
      items = [...items].sort((a, b) => {
        const left = key === "urgency" ? a.urgency : key === "confidence" ? a.confidence ?? -1 : key === "category" ? a.category : key === "status" ? a.status : a.created_at;
        const right = key === "urgency" ? b.urgency : key === "confidence" ? b.confidence ?? -1 : key === "category" ? b.category : key === "status" ? b.status : b.created_at;
        return (left < right ? -1 : left > right ? 1 : 0) * (descending ? -1 : 1);
      });
    }
    const offset = params?.cursor ? Number(params.cursor) : 0;
    const limit = params?.limit ?? 50;
    const page = items.slice(offset, offset + limit);
    const nextOffset = offset + page.length;
    return { items: page, next_cursor: nextOffset < items.length ? String(nextOffset) : null };
  }

  async adjudicateDispute(caseId: string, _idempotencyKey?: string): Promise<CaseResult> {
    await delay();
    return this.getDispute(caseId);
  }

  async fileDispute(_body: FileDisputeRequest, _idempotencyKey?: string): Promise<FileDisputeResponse> {
    await delay();
    return { case_id: "DSP-000049", status: "queued" };
  }

  async approveResolution(caseId: string, note?: string): Promise<CaseResult> {
    await delay();
    const result = await this.getDispute(caseId);
    if (!result.judge) return result;
    const approvedAt = new Date().toISOString();
    return {
      ...result,
      status: "resolved",
      model_proposed_ruling: result.model_proposed_ruling ?? {
        ruling_type: result.judge.ruling_type,
        recommended_action: result.judge.recommended_action,
        author_type: "model",
        decision_origin: "agent",
        author_id: result.judge.provider.display_name ?? null,
        credibility: "model_proposed",
        reason_code: null,
        rationale: result.judge.reasoning,
        approved_at: null,
      },
      reviewer_approved_ruling: {
        ruling_type: result.judge.ruling_type,
        recommended_action: result.judge.recommended_action,
        author_type: "human_reviewer",
        decision_origin: "human",
        author_id: "fixture-reviewer",
        credibility: "higher_than_model_proposed",
        reason_code: null,
        rationale: note ?? null,
        approved_at: approvedAt,
      },
      case_history: [...result.case_history, {
        event: "approved",
        actor_type: "human",
        actor_id: "fixture-reviewer",
        at: approvedAt,
        payload: { note: note ?? "" },
      }],
    };
  }

  async overrideResolution(caseId: string, body: OverrideRequest): Promise<CaseResult> {
    await delay();
    const result = await this.getDispute(caseId);
    if (!result.judge) return result;
    const approvedAt = new Date().toISOString();
    return {
      ...result,
      status: "overridden",
      model_proposed_ruling: result.model_proposed_ruling ?? {
        ruling_type: result.judge.ruling_type,
        recommended_action: result.judge.recommended_action,
        author_type: "model",
        decision_origin: "agent",
        author_id: result.judge.provider.display_name ?? null,
        credibility: "model_proposed",
        reason_code: null,
        rationale: result.judge.reasoning,
        approved_at: null,
      },
      reviewer_approved_ruling: {
        ruling_type: body.ruling_type,
        recommended_action: body.recommended_action,
        reason_code: body.reason_code,
        rationale: body.rationale,
        author_type: "human_reviewer",
        decision_origin: "human",
        author_id: "fixture-reviewer",
        credibility: "higher_than_model_proposed",
        approved_at: approvedAt,
      },
      case_history: [...result.case_history, {
        event: "overridden",
        actor_type: "human",
        actor_id: "fixture-reviewer",
        at: approvedAt,
        payload: {
          ruling_type: body.ruling_type,
          recommended_action: body.recommended_action,
          reason_code: body.reason_code,
          rationale: body.rationale,
          original_ruling_type: result.judge.ruling_type,
        },
      }],
    };
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

  async getMetricsOverview(params: { from: string; to: string; tz?: string }): Promise<MetricsOverview> {
    await delay();
    const cases = [...caseSummaryPage.items, ...archiveSummaries(await this.listArchivedDisputes())]
      .filter((item) => withinDateRange(item.created_at, params.from, `${params.to}T23:59:59.999+08:00`));
    return {
      from: params.from,
      to: params.to,
      timezone: "Asia/Singapore",
      filed: cases.length,
      auto_resolved: cases.filter((item) => item.status === "resolved" && !item.needs_review).length,
      human_intervention: cases.filter((item) => item.needs_review).length,
    };
  }

  async getMetricsTimeseries(params: { from: string; to: string; tz?: string; group_by?: "category" | "status" | "filed_by" | "provider" }): Promise<MetricsTimeseries> {
    await delay();
    const groupBy = params.group_by ?? "category";
    const cases = [...caseSummaryPage.items, ...archiveSummaries(await this.listArchivedDisputes())]
      .filter((item) => withinDateRange(item.created_at, params.from, `${params.to}T23:59:59.999+08:00`));
    const byDate = new Map<string, Map<string, number>>();
    for (const item of cases) {
      const date = singaporeDate(item.created_at);
      const key = dimensionFor(item, groupBy);
      const groups = byDate.get(date) ?? new Map<string, number>();
      groups.set(key, (groups.get(key) ?? 0) + 1);
      byDate.set(date, groups);
    }
    return {
      timezone: "Asia/Singapore",
      granularity: "day",
      group_by: groupBy,
      points: [...byDate.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, groups]) => ({
        date,
        series: [...groups.entries()].map(([key, count]) => ({ key, count })),
      })),
    };
  }

  async getMetricsBreakdown(params: { from: string; to: string; tz?: string; by?: "category" | "status" | "filed_by" | "provider" }): Promise<MetricsBreakdown> {
    await delay();
    const by = params.by ?? "category";
    const cases = [...caseSummaryPage.items, ...archiveSummaries(await this.listArchivedDisputes())]
      .filter((item) => withinDateRange(item.created_at, params.from, `${params.to}T23:59:59.999+08:00`));
    const counts = new Map<string, number>();
    for (const item of cases) {
      const key = dimensionFor(item, by);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return {
      timezone: "Asia/Singapore",
      by,
      slices: [...counts.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, count]) => ({ key, label: key.replaceAll("_", " "), count })),
    };
  }

  async listArchivedDisputes(_limit = 200): Promise<ArchiveDisputePage> {
    await delay();
    const makeCase = (id: number, category: string, origin: "agent" | "human", reviewed: boolean) => {
      // Keep fixture archive IDs globally distinct from the live fixture IDs.
      const archiveCaseId = `DSP-${String(1000 + id).padStart(6, "0")}`;
      const confidence = origin === "human" ? 0.82 : 0.76;
      const proposal = {
        stage: "model_proposed" as const,
        verdict: "refund" as const,
        ruling_type: "refund" as const,
        recommended_action: "Refund the disputed fare.",
        amount_cents: 500,
        currency: "SGD" as const,
        confidence,
        decision_origin: "agent" as const,
        decided_at: "2026-08-10T09:00:00Z",
      };
      const approved = {
        ...proposal,
        stage: "reviewer_approved" as const,
        decision_origin: "human" as const,
        decided_at: "2026-08-11T09:00:00Z",
      };
      return {
        archive_case_id: archiveCaseId,
        // Keep historical ride fixture IDs in the ordinary ride namespace too.
        archive_ride_id: `RIDE-${String(1000 + id).padStart(6, "0")}`,
        category: category as ArchiveDisputePage["items"][number]["category"],
        subject: `Historical ${category.replaceAll("_", " ")} dispute`,
        filed_by: id % 2 ? "rider" as const : "driver" as const,
        created_at: `2026-08-${String(10 + (id % 15)).padStart(2, "0")}T08:30:00Z`,
        policy_version: "ryde-policy-0.1.1",
        status: "resolved" as const,
        verdict: "refund" as const,
        ruling_type: "refund" as const,
        recommended_action: "Refund the disputed fare.",
        amount_cents: 500,
        currency: "SGD" as const,
        confidence,
        decision_origin: origin,
        human_reviewed: reviewed,
        rulings: reviewed ? [proposal, approved] : [proposal],
        synthetic: true,
      };
    };
    const items = [
      makeCase(47, "conduct_complaint", "human", true),
      makeCase(46, "lost_item", "agent", false),
      makeCase(45, "safety_incident", "human", true),
      makeCase(44, "property_damage", "agent", false),
    ];
    return {
      items,
      statistics: { total: items.length, reviewer_approved: 2, model_only: 2, escalated: 0, ongoing: 0 },
    };
  }

  async searchTrips(query = ""): Promise<TripSearchPage> {
    await delay();
    const trips: TripSearchPage["items"] = [
      { ride_id: "RIDE-000123", company_trip_id: null, booked_at: "2026-09-22T07:08:00Z", status: "completed", pickup_label: "Joo Chiat", dropoff_label: "Marina Bay", rider_name: "Sample Rider", driver_name: "Sample Driver" },
      { ride_id: "RIDE-000124", company_trip_id: null, booked_at: "2026-09-22T08:15:00Z", status: "completed", pickup_label: "Tampines", dropoff_label: "Changi Airport", rider_name: "Sample Rider", driver_name: "Sample Driver" },
    ];
    const term = query.toLowerCase();
    return { items: trips.filter((trip) => `${trip.ride_id} ${trip.pickup_label} ${trip.dropoff_label} ${trip.rider_name} ${trip.driver_name}`.toLowerCase().includes(term)) };
  }

  async importCompanyData(_file: File): Promise<ImportResult> {
    await delay();
    return { source_system: "fixture", imported: {}, skipped_duplicate_ids: {} };
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

function withinDateRange(createdAt: string, from?: string, to?: string): boolean {
  const date = singaporeDate(createdAt);
  const fromDate = from ? (from.includes("T") ? singaporeDate(from) : from) : undefined;
  const toDate = to ? (to.includes("T") ? singaporeDate(to) : to) : undefined;
  return (!fromDate || date >= fromDate) && (!toDate || date <= toDate);
}

function singaporeDate(value: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Singapore", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date(value));
  const fields = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${fields.year}-${fields.month}-${fields.day}`;
}

function archiveSummaries(page: ArchiveDisputePage): CaseSummary[] {
  return page.items.map((item) => ({
    case_id: item.archive_case_id,
    case_source: "archive",
    ride_id: item.archive_ride_id,
    category: item.category,
    status: item.status,
    confidence: item.confidence,
    ruling_type: item.ruling_type,
    urgency: 0,
    needs_review: item.human_reviewed || item.status === "pending_review" || item.status === "escalated",
    created_at: item.created_at,
    synthetic_reasoning: false,
    filed_by: item.filed_by,
    provider: null,
  }));
}

function archiveCaseResult(item: ArchiveDisputePage["items"][number]): CaseResult {
  const recordedRuling = (
    ruling: ArchiveDisputePage["items"][number]["rulings"][number],
  ): NonNullable<CaseResult["model_proposed_ruling"]> => ({
    ruling_type: ruling.ruling_type,
    recommended_action: {
      description: ruling.recommended_action,
      amount: { amount_cents: ruling.amount_cents, currency: ruling.currency },
    },
    author_type: ruling.stage === "reviewer_approved" ? "human_reviewer" : "model",
    decision_origin: ruling.decision_origin,
    author_id: null,
    credibility: ruling.stage === "reviewer_approved" ? "higher_than_model_proposed" : "model_proposed",
    reason_code: null,
    rationale: null,
    approved_at: ruling.stage === "reviewer_approved" ? ruling.decided_at : null,
  });
  const proposal = item.rulings.find((ruling) => ruling.stage === "model_proposed");
  const approval = item.rulings.find((ruling) => ruling.stage === "reviewer_approved");
  return {
    case_id: item.archive_case_id,
    case_source: "archive",
    ride_id: item.archive_ride_id,
    category: item.category,
    status: item.status,
    synthetic: item.synthetic,
    synthetic_reasoning: false,
    policy_version: item.policy_version,
    created_at: item.created_at,
    case_facts: { subject: item.subject, filed_by: item.filed_by },
    evidence_audit: null,
    fraud_assessment: null,
    advocates: null,
    judge: null,
    model_proposed_ruling: proposal ? recordedRuling(proposal) : null,
    reviewer_approved_ruling: approval ? recordedRuling(approval) : null,
    external_findings: [],
    external_unavailable: false,
    urgency: 0,
    case_history: [],
  };
}

function dimensionFor(item: CaseSummaryPage["items"][number], dimension: "category" | "status" | "filed_by" | "provider"): string {
  if (dimension === "category") return item.category;
  if (dimension === "status") return item.status;
  if (dimension === "filed_by") return item.filed_by;
  return item.provider ?? "unknown";
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
