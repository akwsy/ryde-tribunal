import createClient from "openapi-fetch";
import type { paths } from "./generated";
import type {
  AdjudicationTrace,
  CaseResult,
  CaseSummaryPage,
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
  ArchiveDisputePage,
} from "./types";

/** Query parameters are derived from the shared Swagger/OpenAPI contract. */
export type ListDisputesParams = NonNullable<paths["/disputes"]["get"]["parameters"]["query"]>;
type ReviewerHeaders = paths["/disputes"]["post"]["parameters"]["header"];

/**
 * Runtime API client backed by the generated OpenAPI paths. The facade keeps
 * the app's friendly method names while request paths, query parameters,
 * headers, and payloads are checked against shared/openapi.yaml.
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

interface ClientOptions {
  baseURL: string;
  reviewerId?: string;
}

interface OpenApiResponse<T> {
  data?: T;
  error?: unknown;
  response: Response;
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
  private readonly baseURL: string;
  private readonly reviewerId: string;
  private readonly api: ReturnType<typeof createClient<paths>>;

  constructor(opts?: Partial<ClientOptions>) {
    this.baseURL = (opts?.baseURL ?? getBaseUrl()).replace(/\/$/, "");
    this.reviewerId = opts?.reviewerId ?? getReviewerId();
    this.api = createClient<paths>({
      // Fixture mode is guarded before every request; this fallback only lets
      // the generated client be constructed when no live API URL is configured.
      baseUrl: this.baseURL || "http://127.0.0.1:8000/api/v1",
    });
  }

  private get isFixtureMode(): boolean {
    return !this.baseURL;
  }

  private async request<T>(call: () => Promise<OpenApiResponse<T>>): Promise<T> {
    if (this.isFixtureMode) {
      throw new Error("Fixture mode: use the fixture provider instead of the live API client.");
    }

    const result = await call();
    if (!result.response.ok || result.error !== undefined) {
      const envelope = result.error as ErrorEnvelope | null;
      throw new ApiError(
        result.response.status,
        envelope?.error?.code ?? "internal_error",
        envelope?.error?.message ?? `HTTP ${result.response.status}`,
        envelope?.error?.details,
      );
    }
    if (result.data === undefined) {
      throw new ApiError(result.response.status, "empty_response", "The API returned no response body.");
    }
    return result.data;
  }

  private withReviewerHeaders(idempotencyKey?: string): ReviewerHeaders {
    return {
      "X-Reviewer-Id": this.reviewerId,
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    };
  }

  async getDispute(caseId: string): Promise<CaseResult> {
    return this.request(() =>
      this.api.GET("/disputes/{case_id}", { params: { path: { case_id: caseId } } }),
    );
  }

  async listDisputes(params?: ListDisputesParams): Promise<CaseSummaryPage> {
    return this.request(() => this.api.GET("/disputes", { params: { query: params } }));
  }

  async adjudicateDispute(caseId: string, idempotencyKey?: string): Promise<CaseResult> {
    return this.request(() =>
      this.api.POST("/disputes/{case_id}/adjudicate", {
        params: {
          path: { case_id: caseId },
          header: this.withReviewerHeaders(idempotencyKey),
        },
      }),
    );
  }

  async fileDispute(body: FileDisputeRequest, idempotencyKey?: string): Promise<FileDisputeResponse> {
    return this.request(() =>
      this.api.POST("/disputes", {
        params: { header: this.withReviewerHeaders(idempotencyKey) },
        body,
      }),
    );
  }

  async approveResolution(caseId: string, note?: string): Promise<CaseResult> {
    return this.request(() =>
      this.api.POST("/disputes/{case_id}/approve", {
        params: {
          path: { case_id: caseId },
          header: this.withReviewerHeaders(),
        },
        body: { note },
      }),
    );
  }

  async overrideResolution(caseId: string, body: OverrideRequest): Promise<CaseResult> {
    return this.request(() =>
      this.api.POST("/disputes/{case_id}/override", {
        params: {
          path: { case_id: caseId },
          header: this.withReviewerHeaders(),
        },
        body,
      }),
    );
  }

  async getAdjudicationTrace(caseId: string): Promise<AdjudicationTrace> {
    return this.request(() =>
      this.api.GET("/disputes/{case_id}/trace", { params: { path: { case_id: caseId } } }),
    );
  }

  async getCaseHistory(caseId: string): Promise<HistoryEvent[]> {
    return this.request(() =>
      this.api.GET("/disputes/{case_id}/history", { params: { path: { case_id: caseId } } }),
    );
  }

  async getEvidence(evidenceId: string): Promise<Evidence> {
    return this.request(() =>
      this.api.GET("/evidence/{evidence_id}", { params: { path: { evidence_id: evidenceId } } }),
    );
  }

  async getMetricsOverview(params: {
    from: string;
    to: string;
    tz?: "Asia/Singapore";
  }): Promise<MetricsOverview> {
    return this.request(() => this.api.GET("/metrics/overview", { params: { query: params } }));
  }

  async getMetricsTimeseries(params: {
    from: string;
    to: string;
    tz?: "Asia/Singapore";
    group_by?: "category" | "status" | "filed_by" | "provider";
  }): Promise<MetricsTimeseries> {
    return this.request(() => this.api.GET("/metrics/timeseries", { params: { query: params } }));
  }

  async getMetricsBreakdown(params: {
    from: string;
    to: string;
    tz?: "Asia/Singapore";
    by?: "category" | "status" | "filed_by" | "provider";
  }): Promise<MetricsBreakdown> {
    return this.request(() => this.api.GET("/metrics/breakdown", { params: { query: params } }));
  }

  async listArchivedDisputes(limit = 200): Promise<ArchiveDisputePage> {
    return this.request(() => this.api.GET("/archive/disputes", { params: { query: { limit } } }));
  }

  async searchTrips(query = "", limit = 20): Promise<TripSearchPage> {
    return this.request(() => this.api.GET("/trips", { params: { query: { query, limit } } }));
  }

  async importCompanyData(file: File): Promise<ImportResult> {
    // openapi-typescript represents `format: binary` as string. Fetch accepts
    // File as a binary BodyInit; this narrow cast bridges that schema mapping.
    return this.request(() =>
      this.api.POST("/imports/company-data", {
        params: {
          header: this.withReviewerHeaders(crypto.randomUUID()),
        },
        headers: { "Content-Type": "application/zip" },
        body: file as unknown as string,
      }),
    );
  }

  async getPolicy(version: string): Promise<PolicyDocument> {
    return this.request(() => this.api.GET("/policy/{version}", { params: { path: { version } } }));
  }

  async getHealth(): Promise<Health> {
    return this.request(() => this.api.GET("/health"));
  }
}

let _client: TribunalClient | null = null;

export function getClient(): TribunalClient {
  if (!_client) _client = new TribunalClient();
  return _client;
}
