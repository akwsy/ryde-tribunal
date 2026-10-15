import { describe, expect, it, vi } from "vitest";
import { TribunalClient } from "@/lib/api/client";
import { FixtureClient } from "@/lib/api/fixture-client";

describe("frontend API methods", () => {
  it("opens fixture historical detail with stored rulings and no live judge", async () => {
    const result = await new FixtureClient().getDispute("DSP-001047");

    expect(result.case_source).toBe("archive");
    expect(result.case_id).toBe("DSP-001047");
    expect(result.judge).toBeNull();
    expect(result.advocates).toBeNull();
    expect(result.model_proposed_ruling?.ruling_type).toBe("refund");
    expect(result.reviewer_approved_ruling?.credibility).toBe("higher_than_model_proposed");
  });

  it("sends the inclusive Singapore range and approved grouping to metrics endpoints", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new TribunalClient({ baseURL: "http://localhost/api/v1" });

    await client.getMetricsOverview({ from: "2026-09-01", to: "2026-09-30", tz: "Asia/Singapore" });
    await client.getMetricsTimeseries({ from: "2026-09-01", to: "2026-09-30", tz: "Asia/Singapore", group_by: "filed_by" });
    await client.getMetricsBreakdown({ from: "2026-09-01", to: "2026-09-30", tz: "Asia/Singapore", by: "provider" });

    const urls = fetchMock.mock.calls.map(([input]) => new URL(input instanceof Request ? input.url : String(input)));
    expect(urls[0].searchParams.get("from")).toBe("2026-09-01");
    expect(urls[0].searchParams.get("to")).toBe("2026-09-30");
    expect(urls[0].searchParams.get("tz")).toBe("Asia/Singapore");
    expect(urls[1].searchParams.get("group_by")).toBe("filed_by");
    expect(urls[2].searchParams.get("by")).toBe("provider");
  });

  it("searches by trip ID/details and uploads ZIP bytes with the contract content type", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ items: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new TribunalClient({ baseURL: "http://localhost/api/v1", reviewerId: "reviewer-test" });

    await client.searchTrips("Joo Chiat", 20);
    const firstInput = fetchMock.mock.calls[0][0];
    const searchUrl = new URL(firstInput instanceof Request ? firstInput.url : String(firstInput));
    expect(searchUrl.pathname).toBe("/api/v1/trips");
    expect(searchUrl.searchParams.get("query")).toBe("Joo Chiat");
    expect(searchUrl.searchParams.get("limit")).toBe("20");

    fetchMock.mockImplementationOnce(async () => new Response(JSON.stringify({ source_system: "test", imported: {}, skipped_duplicate_ids: {} }), { status: 200 }));
    await client.importCompanyData(new File(["fake zip bytes"], "company-data.zip", { type: "application/zip" }));
    const [input, init] = fetchMock.mock.calls[1];
    const requestUrl = input instanceof Request ? input.url : String(input);
    const requestHeaders = input instanceof Request ? input.headers : new Headers(init?.headers);
    expect(requestUrl).toBe("http://localhost/api/v1/imports/company-data");
    expect(requestHeaders.get("Content-Type")).toBe("application/zip");
    expect(requestHeaders.get("X-Reviewer-Id")).toBe("reviewer-test");
  });
});
