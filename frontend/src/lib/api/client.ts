import type {
  CaseResult,
  CaseSummaryPage,
  CaseStatus,
  Category,
  Evidence,
  ErrorEnvelope,
  FileDisputeRequest,
  FileDisputeResponse,
  Health,
  ImportResult,
  HistoryEvent,
  MetricsBreakdown,
  MetricsOverview,
  MetricsTimeseries,
  OverrideRequest,
  PolicyDocument,
  TripSearchPage,
} from "./types";

/**
 * Typed API client. Every method maps to exactly one documented endpoint in
 * docs/02-api-contract.md §2 (shared/openapi.yaml).
 *
 * Base URL from NEXT_PUBLIC_API_BASE_URL. When that is unset, the client falls
 * back to the fixture layer — but the fixture layer is a separate module so the
 * client itself never hardcodes a result.
 */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ListDisputesParams {
  status?: CaseStatus;
  category?: Category;
  urgency_min?: number;
  needs_review?: boolean;
  from?: string;
  to?: string;
  sort?: string;
  limit?: number;
  cursor?: string;
}

interface ClientOptions {
  baseURL: string;
  reviewerId?: string;
}

function getBaseUrl(): string {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL;
  }
  return "";
}

function getReviewerId(): string {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_REVIEWER_ID) {
    return process.env.NEXT_PUBLIC_REVIEWER_ID;
  }
  return "reviewer-default";
}

export class TribunalClient {
  private baseURL: string;
  private reviewerId: string;

  constructor(opts?: Partial<ClientOptions>) {
    this.baseURL = (opts?.baseURL ?? getBaseUrl()).replace(/\/$/, "");
    this.reviewerId = opts?.reviewerId ?? getReviewerId();
  }

  private get isFixtureMode(): boolean {
    return !this.baseURL;
  }

  private buildUrl(path: string): string {
    return `${this.baseURL}${path}`;
  }

  private async request<T>(
    path: string,
    init?: RequestInit & { skipParse?: boolean },
  ): Promise<T> {
    if (this.isFixtureMode) {
      throw new Error(
        "Fixture mode: client should not be called directly. Use the fixture provider.",
      );
    }

    const url = this.buildUrl(path);
    const res = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });

    if (res.status === 204) {
      return undefined as T;
    }

    const body = await res.json().catch(() => null);

    if (!res.ok) {
      const errorEnvelope = body as ErrorEnvelope | null;
      throw new ApiError(
        res.status,
        errorEnvelope?.error?.code ?? "internal_error",
        errorEnvelope?.error?.message ?? `HTTP ${res.status}`,
        errorEnvelope?.error?.details,
      );
    }

    return body as T;
  }

  private withReviewerHeaders(extra?: Record<string, string>): Record<string, string> {
    return {
      "X-Reviewer-Id": this.reviewerId,
      ...(extra ?? {}),
    };
  }

  // ── GET /disputes/{case_id} ──────────────────────────────────────────────
  async getDispute(caseId: string): Promise<CaseResult> {
    return this.request<CaseResult>(`/disputes/${encodeURIComponent(caseId)}`);
  }

  // ── GET /disputes ─────────────────────────────────────────────────────────
  async listDisputes(params?: ListDisputesParams): Promise<CaseSummaryPage> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.category) qs.set("category", params.category);
    if (params?.urgency_min !== undefined) qs.set("urgency_min", String(params.urgency_min));
    if (params?.needs_review !== undefined) qs.set("needs_review", String(params.needs_review));
    if (params?.from) qs.set("from", params.from);
    if (params?.to) qs.set("to", params.to);
    if (params?.sort) qs.set("sort", params.sort);
    if (params?.limit !== undefined) qs.set("limit", String(params.limit));
    if (params?.cursor) qs.set("cursor", params.cursor);
    const query = qs.toString();
    return this.request<CaseSummaryPage>(`/disputes${query ? `?${query}` : ""}`);
  }

  // ── POST /disputes/{case_id}/adjudicate ──────────────────────────────────
  async adjudicateDispute(caseId: string, idempotencyKey?: string): Promise<CaseResult> {
    const headers: Record<string, string> = {};
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
    return this.request<CaseResult>(`/disputes/${encodeURIComponent(caseId)}/adjudicate`, {
      method: "POST",
      headers: this.withReviewerHeaders(headers),
    });
  }

  // ── POST /disputes ────────────────────────────────────────────────────────
  async fileDispute(body: FileDisputeRequest, idempotencyKey?: string): Promise<FileDisputeResponse> {
    const headers: Record<string, string> = {};
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
    return this.request<FileDisputeResponse>(`/disputes`, {
      method: "POST",
      headers: this.withReviewerHeaders(headers),
      body: JSON.stringify(body),
    });
  }

  // ── POST /disputes/{case_id}/approve ─────────────────────────────────────
  async approveResolution(caseId: string, note?: string): Promise<CaseResult> {
    return this.request<CaseResult>(`/disputes/${encodeURIComponent(caseId)}/approve`, {
      method: "POST",
      headers: this.withReviewerHeaders(),
      body: JSON.stringify({ note }),
    });
  }

  // ── POST /disputes/{case_id}/override ────────────────────────────────────
  async overrideResolution(caseId: string, body: OverrideRequest): Promise<CaseResult> {
    return this.request<CaseResult>(`/disputes/${encodeURIComponent(caseId)}/override`, {
      method: "POST",
      headers: this.withReviewerHeaders(),
      body: JSON.stringify(body),
    });
  }

  // ── GET /disputes/{case_id}/history ───────────────────────────────────────
  async getCaseHistory(caseId: string): Promise<HistoryEvent[]> {
    return this.request<HistoryEvent[]>(`/disputes/${encodeURIComponent(caseId)}/history`);
  }

  // ── GET /evidence/{evidence_id} ───────────────────────────────────────────
  async getEvidence(evidenceId: string): Promise<Evidence> {
    return this.request<Evidence>(`/evidence/${encodeURIComponent(evidenceId)}`);
  }

  // ── GET /metrics/overview ──────────────────────────────────────────────────
  async getMetricsOverview(params: { from: string; to: string; tz?: string }): Promise<MetricsOverview> {
    const qs = new URLSearchParams({ from: params.from, to: params.to, tz: params.tz ?? "Asia/Singapore" });
    return this.request<MetricsOverview>(`/metrics/overview?${qs.toString()}`);
  }

  // ── GET /metrics/timeseries ────────────────────────────────────────────────
  async getMetricsTimeseries(params: {
    from: string;
    to: string;
    tz?: string;
    group_by?: "category" | "status" | "filed_by" | "provider";
  }): Promise<MetricsTimeseries> {
    const qs = new URLSearchParams({
      from: params.from,
      to: params.to,
      tz: params.tz ?? "Asia/Singapore",
      group_by: params.group_by ?? "category",
    });
    return this.request<MetricsTimeseries>(`/metrics/timeseries?${qs.toString()}`);
  }

  async getMetricsBreakdown(params: {
    from: string;
    to: string;
    tz?: string;
    by?: "category" | "status" | "filed_by" | "provider";
  }): Promise<MetricsBreakdown> {
    const qs = new URLSearchParams({
      from: params.from,
      to: params.to,
      tz: params.tz ?? "Asia/Singapore",
      by: params.by ?? "category",
    });
    return this.request<MetricsBreakdown>(`/metrics/breakdown?${qs.toString()}`);
  }

  async searchTrips(query = "", limit = 20): Promise<TripSearchPage> {
    const qs = new URLSearchParams({ query, limit: String(limit) });
    return this.request<TripSearchPage>(`/trips?${qs.toString()}`);
  }

  async importCompanyData(file: File): Promise<ImportResult> {
    if (this.isFixtureMode) {
      throw new Error("Fixture mode: use the fixture provider for imports.");
    }
    const url = this.buildUrl("/imports/company-data");
    const response = await fetch(url, {
      method: "POST",
      headers: this.withReviewerHeaders({
        "Content-Type": "application/zip",
        "Idempotency-Key": crypto.randomUUID(),
      }),
      body: file,
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const errorEnvelope = body as ErrorEnvelope | null;
      throw new ApiError(
        response.status,
        errorEnvelope?.error?.code ?? "internal_error",
        errorEnvelope?.error?.message ?? `HTTP ${response.status}`,
        errorEnvelope?.error?.details,
      );
    }
    return body as ImportResult;
  }

  // ── GET /policy/{version} ─────────────────────────────────────────────────
  async getPolicy(version: string): Promise<PolicyDocument> {
    return this.request<PolicyDocument>(`/policy/${encodeURIComponent(version)}`);
  }

  // ── GET /health ────────────────────────────────────────────────────────────
  async getHealth(): Promise<Health> {
    return this.request<Health>(`/health`);
  }
}

// ── Singleton ────────────────────────────────────────────────────────────────
let _client: TribunalClient | null = null;

export function getClient(): TribunalClient {
  if (!_client) {
    _client = new TribunalClient();
  }
  return _client;
}
