"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getActiveClient } from "@/lib/api/fixture-client";
import type { CaseStatus, CaseSummary, MetricsBreakdown, MetricsOverview, MetricsTimeseries } from "@/lib/api/types";
import { labelForCaseStatus, labelForCategory, labelForRulingType } from "@/lib/api/format";
import { presetRange, type DateRange, type PeriodChoice } from "@/lib/dashboard-dates";
import { isGuestDemo } from "@/lib/demo-session";

const DIMENSIONS = ["category", "status", "filed_by", "provider"] as const;
type Dimension = (typeof DIMENSIONS)[number];
const COLORS = ["#0f766e", "#2563eb", "#c2410c", "#7c3aed", "#be123c", "#4d7c0f", "#a16207"];
const CASES_PER_PAGE = 15;

interface DashboardData {
  overview: MetricsOverview;
  timeseries: MetricsTimeseries;
  breakdown: MetricsBreakdown;
  cases: CaseSummary[];
}
type QueueTab = "all" | "unreviewed" | "under_review" | "decided" | "human_review";

export function ReviewerDashboard() {
  const [period, setPeriod] = useState<PeriodChoice>("day");
  const [range, setRange] = useState<DateRange | null>(null);
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [dimension, setDimension] = useState<Dimension>("category");
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [urgencyFilter, setUrgencyFilter] = useState("all");
  const [sort, setSort] = useState("date-desc");
  const [search, setSearch] = useState("");
  const [casePage, setCasePage] = useState(0);
  const [queueTab, setQueueTab] = useState<QueueTab>("all");
  const [processingIds, setProcessingIds] = useState<Set<string>>(new Set());
  const autoStarted = useRef(new Set<string>());

  const load = useCallback(async (selectedRange: DateRange, selectedDimension: Dimension) => {
    setLoading(true);
    setError(null);
    try {
      const client = getActiveClient();
      const query = {
        from: selectedRange.from,
        to: selectedRange.to,
        tz: "Asia/Singapore" as const,
      };
      const [overview, timeseries, breakdown, cases] = await Promise.all([
        client.getMetricsOverview(query),
        client.getMetricsTimeseries({ ...query, group_by: selectedDimension }),
        client.getMetricsBreakdown({ ...query, by: selectedDimension }),
        loadAllCases(),
      ]);
      setData({ overview, timeseries, breakdown, cases });
    } catch (cause) {
      setData(null);
      setError(cause instanceof Error ? cause.message : "Unable to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!range) {
      setRange(presetRange("day"));
      return;
    }
    void load(range, dimension);
  }, [range, dimension, load]);

  // A reviewer opening the workspace starts any queued live filings. The server's
  // atomic processing claim plus the stable idempotency key prevents duplicate runs
  // when another browser opens the dashboard at the same time.
  useEffect(() => {
    if (!data || isGuestDemo()) return;
    const pending = data.cases.filter((item) =>
      item.case_source === "live" && item.status === "queued" && !autoStarted.current.has(item.case_id),
    );
    if (!pending.length) return;
    for (const item of pending) autoStarted.current.add(item.case_id);
    setProcessingIds((current) => new Set([...current, ...pending.map((item) => item.case_id)]));

    let next = 0;
    const workers = Array.from({ length: Math.min(2, pending.length) }, async () => {
      while (next < pending.length) {
        const item = pending[next++];
        try {
          await getActiveClient().adjudicateDispute(item.case_id, `dashboard-auto-${item.case_id}`);
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : `Could not start review for ${item.case_id}.`);
        } finally {
          setProcessingIds((current) => {
            const updated = new Set(current);
            updated.delete(item.case_id);
            return updated;
          });
        }
      }
    });
    void Promise.all(workers).then(async () => {
      try {
        const cases = await loadAllCases();
        setData((current) => current ? { ...current, cases } : current);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Could not refresh case statuses.");
      }
    });
  }, [data]);

  useEffect(() => {
    if (!data) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      void loadAllCases().then((cases) => {
        setData((current) => current ? { ...current, cases } : current);
      }).catch((cause) => {
        setError(cause instanceof Error ? cause.message : "Could not refresh incoming disputes.");
      });
    }, 5000);
    return () => window.clearInterval(timer);
  }, [data]);

  function choosePeriod(choice: Exclude<PeriodChoice, "custom">) {
    setPeriod(choice);
    setRange(presetRange(choice));
  }

  function applyCustomRange() {
    if (!customFrom || !customTo || customFrom > customTo) {
      setError("Choose a valid inclusive start and end date.");
      return;
    }
    setPeriod("custom");
    setRange({ from: customFrom, to: customTo });
  }

  const visibleCases = useMemo(() => {
    if (!data) return [];
    const query = search.trim().toLocaleLowerCase();
    const list = data.cases.filter((item) =>
      (categoryFilter === "all" || item.category === categoryFilter) &&
      (queueTab === "all" ||
        (queueTab === "unreviewed" && item.status === "queued") ||
        (queueTab === "under_review" && (item.status === "processing" || processingIds.has(item.case_id))) ||
        (queueTab === "decided" && (item.status === "resolved" || item.status === "overridden")) ||
        (queueTab === "human_review" && (item.status === "escalated" || item.status === "pending_review"))) &&
      (urgencyFilter === "all" || urgencyFilter === "not_urgent") &&
      (!query || [item.case_id, item.ride_id, item.category, item.status, item.ruling_type ?? ""]
        .some((value) => value.toLocaleLowerCase().includes(query))),
    );
    return list.sort((a, b) => {
      if (sort === "date-asc") return a.created_at.localeCompare(b.created_at);
      if (sort === "category") return a.category.localeCompare(b.category) || a.created_at.localeCompare(b.created_at);
      if (sort === "status") return a.status.localeCompare(b.status) || a.created_at.localeCompare(b.created_at);
      if (sort === "urgency") return 0;
      return b.created_at.localeCompare(a.created_at);
    });
  }, [categoryFilter, data, processingIds, queueTab, search, sort, urgencyFilter]);

  const queueCounts = useMemo(() => {
    const counts: Record<Exclude<QueueTab, "all">, number> = {
      unreviewed: 0, under_review: 0, decided: 0, human_review: 0,
    };
    for (const item of data?.cases ?? []) {
      const status = processingIds.has(item.case_id) ? "processing" : item.status;
      if (status === "queued") counts.unreviewed += 1;
      else if (status === "processing") counts.under_review += 1;
      else if (status === "resolved" || status === "overridden") counts.decided += 1;
      else if (status === "escalated" || status === "pending_review") counts.human_review += 1;
    }
    return counts;
  }, [data, processingIds]);

  const pageCount = Math.max(1, Math.ceil(visibleCases.length / CASES_PER_PAGE));
  const pageCases = visibleCases.slice(casePage * CASES_PER_PAGE, (casePage + 1) * CASES_PER_PAGE);

  const chartData = useMemo(() => {
    if (!data) return [];
    const keys = [...new Set(data.timeseries.points.flatMap((point) => point.series.map((series) => series.key)))];
    return data.timeseries.points.map((point) => ({
      date: point.date,
      ...Object.fromEntries(keys.map((key) => [key, point.series.find((item) => item.key === key)?.count ?? 0])),
    }));
  }, [data]);

  return (
    <main className="mx-auto max-w-7xl px-5 py-8 text-slate-900 sm:px-8">
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">Ryde Tribunal</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Reviewer dashboard</h1>
          <p className="mt-1 text-slate-600">New disputes are reviewed automatically when this workspace opens.</p>
        </div>
        <nav aria-label="Reviewer tools" className="flex gap-2">
          <Link className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-100" href="/file-dispute">Simulate filing</Link>
          <Link className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-100" href="/import-data">Import company data</Link>
        </nav>
      </header>

      <section aria-labelledby="period-heading" className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 id="period-heading" className="font-semibold">Choose a date range</h2>
            <p className="text-sm text-slate-600">Both dates are included. Weeks start Sunday.</p>
          </div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Dashboard period">
            {(["day", "week", "month"] as const).map((choice) => (
              <button key={choice} type="button" onClick={() => choosePeriod(choice)} aria-pressed={period === choice}
                className={`rounded-md px-3 py-2 text-sm capitalize ${period === choice ? "bg-teal-700 text-white" : "border border-slate-300 hover:bg-slate-100"}`}>
                {choice === "day" ? "Today" : `This ${choice}`}
              </button>
            ))}
            <button type="button" onClick={() => setPeriod("custom")} aria-pressed={period === "custom"}
              className={`rounded-md px-3 py-2 text-sm ${period === "custom" ? "bg-teal-700 text-white" : "border border-slate-300 hover:bg-slate-100"}`}>Custom</button>
          </div>
        </div>
        {period === "custom" && <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="text-sm">From (inclusive)<input aria-label="Custom range start" type="date" value={customFrom} onChange={(event) => setCustomFrom(event.target.value)} className="mt-1 block rounded border border-slate-300 px-3 py-2" /></label>
          <label className="text-sm">To (inclusive)<input aria-label="Custom range end" type="date" value={customTo} onChange={(event) => setCustomTo(event.target.value)} className="mt-1 block rounded border border-slate-300 px-3 py-2" /></label>
          <button type="button" onClick={applyCustomRange} className="rounded-md bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800">Apply range</button>
        </div>}
        {range && <p className="mt-3 text-sm text-slate-600">{range.from} to {range.to} (Asia/Singapore)</p>}
      </section>

      {loading && <p role="status" className="mb-4 text-sm text-slate-600">Loading dashboard…</p>}
      {error && <p role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</p>}

      {data && <>
        {data.overview.filed === 0 && <section className="mb-6 rounded-xl border border-teal-200 bg-teal-50 p-6" aria-label="No cases in selected period" data-testid="empty-period-state">
          <h2 className="font-semibold text-teal-950">No disputes filed in this period</h2>
          <p className="mt-2 text-sm text-teal-900">Try the demonstration period or choose another range. Today remains the default.</p>
          <button type="button" data-testid="demo-period-button" aria-label="Open the synthetic demonstration period (12 to 13 October 2026)" className="mt-4 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700" onClick={() => {
            const demo = { from: process.env.NEXT_PUBLIC_DEMO_FROM || "2026-10-12", to: process.env.NEXT_PUBLIC_DEMO_TO || "2026-10-13" };
            setPeriod("custom"); setCustomFrom(demo.from); setCustomTo(demo.to); setRange(demo);
          }}>Open demonstration period</button>
        </section>}
        <section aria-label="Case totals" className="mb-6 grid gap-4 sm:grid-cols-3">
          <StatCard label="Cases filed" value={data.overview.filed} hint="In selected filing-date range" />
          <StatCard label="Automatically resolved" value={data.overview.auto_resolved} hint="Judge was confident" />
          <StatCard label="Human review" value={data.overview.human_intervention} hint="Awaiting reviewer or escalated" />
        </section>

        <section className="mb-7 grid gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,1fr)]">
          <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
              <div><h2 className="font-semibold">Cases filed over time</h2><p className="text-sm text-slate-600">Grouped by {dimensionLabel(dimension).toLowerCase()} · {data.timeseries.granularity} buckets</p></div>
            </div>
            <div className="h-72" role="img" aria-label={`Line chart of filed cases grouped by ${dimensionLabel(dimension).toLowerCase()}`}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Legend />
                  {chartKeys(chartData).map((key, index) => <Line key={key} type="monotone" dataKey={key} name={dimensionValueLabel(dimension, key)} stroke={COLORS[index % COLORS.length]} strokeWidth={2} dot={{r:3}} isAnimationActive={false} />)}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <details className="mt-3 text-xs text-slate-600"><summary className="cursor-pointer">View chart data as text</summary><table className="mt-2 w-full text-left"><caption className="sr-only">Case activity counts</caption><thead><tr><th>Date</th><th>Counts</th></tr></thead><tbody>{data.timeseries.points.map(point => <tr key={point.date}><th className="py-1 font-normal">{point.date}</th><td>{point.series.map(item => `${dimensionValueLabel(dimension,item.key)}: ${item.count}`).join("; ") || "0 cases"}</td></tr>)}</tbody></table></details>
          </article>
          <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div><h2 className="font-semibold">Case breakdown</h2><p className="text-sm text-slate-600">Same filing-date range</p></div>
              <label className="text-sm">Group by <select aria-label="Pie chart grouping" value={dimension} onChange={(event) => setDimension(event.target.value as Dimension)} className="ml-1 rounded border border-slate-300 px-2 py-1">
                {DIMENSIONS.map((item) => <option key={item} value={item}>{dimensionLabel(item)}</option>)}
              </select></label>
            </div>
            <div className="h-64" role="img" aria-label={`Pie chart of cases grouped by ${dimensionLabel(dimension).toLowerCase()}`}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart><Pie data={data.breakdown.slices} dataKey="count" nameKey="label" cx="50%" cy="50%" innerRadius={55} outerRadius={86} isAnimationActive={false} label={false}>
                  {data.breakdown.slices.map((slice, index) => <Cell key={slice.key} fill={COLORS[index % COLORS.length]} />)}
                </Pie><Tooltip /><Legend /></PieChart>
              </ResponsiveContainer>
            </div>
            <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600" aria-label="Case breakdown counts">{data.breakdown.slices.map(slice => <li key={slice.key}>{slice.label}: {slice.count}</li>)}</ul>
          </article>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 p-5">
            <div className="mb-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-5" role="group" aria-label="Case review queues">
              {([
                ["all", "All cases", data.cases.length],
                ["unreviewed", "Not reviewed", queueCounts.unreviewed],
                ["under_review", "Under review", queueCounts.under_review],
                ["decided", "Decision decided", queueCounts.decided],
                ["human_review", "Needs human review", queueCounts.human_review],
              ] as const).map(([key, label, count]) => (
                <button key={key} type="button" aria-pressed={queueTab === key} onClick={() => { setQueueTab(key); setCasePage(0); }}
                  className={`flex items-center justify-between rounded-lg border px-3 py-3 text-left text-sm ${queueTab === key ? "border-teal-700 bg-teal-50 text-teal-950" : "border-slate-200 hover:bg-slate-50"}`}>
                  <span className="flex items-center gap-2">
                    {key === "under_review" && count > 0 && <span aria-hidden="true" className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-teal-700 border-t-transparent" />}
                    {label}
                  </span>
                  <strong className="tabular-nums">{count}</strong>
                </button>
              ))}
            </div>
            {queueCounts.under_review > 0 && <p className="mb-4 flex items-center gap-2 text-sm text-teal-800" role="status">
              <span aria-hidden="true" className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-teal-700 border-t-transparent" />
              Agents are checking case evidence and preparing a recommendation.
            </p>}
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><h2 className="text-lg font-semibold">{queueHeading(queueTab)}</h2><p className="text-sm text-slate-600">{data.cases.length} total · list includes all filing dates; charts use the selected period</p></div>
              <div className="flex flex-wrap gap-2">
                <label className="sr-only" htmlFor="search-cases">Search cases</label><input id="search-cases" type="search" value={search} onChange={(event) => { setSearch(event.target.value); setCasePage(0); }} placeholder="Search case, ride, or outcome" className="min-w-48 rounded border border-slate-300 px-3 py-2 text-sm" />
                <label className="sr-only" htmlFor="filter-category">Filter category</label><select id="filter-category" aria-label="Filter by category" value={categoryFilter} onChange={(event) => { setCategoryFilter(event.target.value); setCasePage(0); }} className="rounded border border-slate-300 px-2 py-2 text-sm"><option value="all">All categories</option>{allCategories().map((category) => <option key={category} value={category}>{labelForCategory(category)}</option>)}</select>
                <label className="sr-only" htmlFor="filter-urgency">Filter urgency</label><select id="filter-urgency" aria-label="Filter by urgency" value={urgencyFilter} onChange={(event) => setUrgencyFilter(event.target.value)} className="rounded border border-slate-300 px-2 py-2 text-sm"><option value="all">All urgency</option><option value="not_urgent">Not urgent</option></select>
                <label className="sr-only" htmlFor="sort-cases">Sort cases</label><select id="sort-cases" aria-label="Sort cases" value={sort} onChange={(event) => { setSort(event.target.value); setCasePage(0); }} className="rounded border border-slate-300 px-2 py-2 text-sm"><option value="date-desc">Newest filed</option><option value="date-asc">Oldest filed</option><option value="category">Category</option><option value="status">Status</option><option value="urgency">Urgency</option></select>
              </div>
            </div>
          </div>
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Case table; scroll horizontally to view all columns">
            <table className="w-full min-w-[780px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3">Case</th><th className="px-4 py-3">Category</th><th className="px-4 py-3">Filed</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Outcome</th><th className="px-4 py-3">Review</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {pageCases.map((item) => {
                  const caseLabel = <Link className="font-semibold text-teal-800 hover:underline" href={`/cases/${encodeURIComponent(item.case_id)}`}>{item.case_id}</Link>;
                  const status = processingIds.has(item.case_id) ? "processing" : item.status;
                  return <tr key={item.case_id} className="hover:bg-slate-50"><td className="px-5 py-4">{caseLabel}<div className="text-xs text-slate-500">{item.ride_id} · filed by {item.filed_by}</div></td><td className="px-4 py-4">{labelForCategory(item.category)}</td><td className="px-4 py-4">{new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore" }).format(new Date(item.created_at))}</td><td className="px-4 py-4">{status === "processing" ? <span className="inline-flex items-center gap-2 text-teal-800"><span aria-hidden="true" className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-teal-700 border-t-transparent" />Under review</span> : labelForCaseStatus(status)}</td><td className="px-4 py-4">{item.ruling_type ? labelForRulingType(item.ruling_type) : status === "processing" ? "Agents reviewing" : "Awaiting decision"}</td><td className="px-4 py-4">{status === "processing" ? "In progress" : item.needs_review ? "Human review" : status === "queued" ? "Not reviewed" : "Decision decided"}</td></tr>;
                })}
                {visibleCases.length === 0 && <tr><td colSpan={6} className="px-5 py-10 text-center text-slate-500">No cases match these filters.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-5 py-4 text-sm">
            <p className="text-slate-600">Showing {visibleCases.length === 0 ? 0 : casePage * CASES_PER_PAGE + 1}–{Math.min((casePage + 1) * CASES_PER_PAGE, visibleCases.length)} of {visibleCases.length}</p>
            <div className="flex items-center gap-2"><button type="button" className="rounded border border-slate-300 px-3 py-2 disabled:opacity-40" disabled={casePage === 0} onClick={() => setCasePage((page) => Math.max(0, page - 1))}>Previous</button><span aria-live="polite">Page {casePage + 1} of {pageCount}</span><button type="button" className="rounded border border-slate-300 px-3 py-2 disabled:opacity-40" disabled={casePage + 1 >= pageCount} onClick={() => setCasePage((page) => Math.min(pageCount - 1, page + 1))}>Next</button></div>
          </div>
        </section>
      </>}
    </main>
  );
}

async function loadAllCases(): Promise<CaseSummary[]> {
  const client = getActiveClient();
  const items: CaseSummary[] = [];
  let cursor: string | undefined;
  do {
    const page = await client.listDisputes({
      limit: 200,
      cursor,
    });
    items.push(...page.items);
    cursor = page.next_cursor ?? undefined;
  } while (cursor);
  return items;
}

function StatCard({ label, value, hint }: { label: string; value: number; hint: string }) {
  return <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><p className="text-sm font-medium text-slate-600">{label}</p><p className="mt-2 text-3xl font-bold tabular-nums">{value.toLocaleString("en-SG")}</p><p className="mt-1 text-xs text-slate-500">{hint}</p></article>;
}

function dimensionLabel(value: Dimension): string {
  return { category: "Category", status: "Status", filed_by: "Filing party", provider: "Provider" }[value];
}

function queueHeading(value: QueueTab): string {
  return {
    all: "All cases",
    unreviewed: "Not reviewed",
    under_review: "Under review",
    decided: "Verdict decided",
    human_review: "Requires further human evaluation",
  }[value];
}

function dimensionValueLabel(dimension: Dimension, value: string): string {
  if (dimension === "category") return labelForCategory(value);
  if (dimension === "status") return labelForCaseStatus(value);
  if (dimension === "filed_by") return value === "rider" ? "Rider" : value === "driver" ? "Driver" : "Unknown";
  return value === "unknown" ? "Unknown provider" : value;
}

function chartKeys(data: Array<Record<string, unknown>>): string[] {
  if (data.length === 0) return [];
  return Object.keys(data[0]).filter((key) => key !== "date");
}

function allCategories() {
  return ["route_deviation", "no_show_charge", "fare_calculation", "other_cancellation_fee", "property_damage", "safety_incident", "lost_item", "conduct_complaint"] as const;
}
