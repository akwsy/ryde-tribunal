"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
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
import { labelForCaseStatus, labelForCategory } from "@/lib/api/format";
import { presetRange, singaporeBoundary, type DateRange, type PeriodChoice } from "@/lib/dashboard-dates";

const DIMENSIONS = ["category", "status", "filed_by", "provider"] as const;
type Dimension = (typeof DIMENSIONS)[number];
const COLORS = ["#0f766e", "#2563eb", "#c2410c", "#7c3aed", "#be123c", "#4d7c0f", "#a16207"];

interface DashboardData {
  overview: MetricsOverview;
  timeseries: MetricsTimeseries;
  breakdown: MetricsBreakdown;
  cases: CaseSummary[];
}

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
  const [statusFilter, setStatusFilter] = useState("all");
  const [urgencyFilter, setUrgencyFilter] = useState("all");
  const [sort, setSort] = useState("date-desc");

  const load = useCallback(async (selectedRange: DateRange, selectedDimension: Dimension) => {
    setLoading(true);
    setError(null);
    try {
      const client = getActiveClient();
      const query = {
        from: selectedRange.from,
        to: selectedRange.to,
        tz: "Asia/Singapore",
      };
      const [overview, timeseries, breakdown, cases] = await Promise.all([
        client.getMetricsOverview(query),
        client.getMetricsTimeseries({ ...query, group_by: selectedDimension }),
        client.getMetricsBreakdown({ ...query, by: selectedDimension }),
        loadAllCases(selectedRange),
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
    const list = data.cases.filter((item) =>
      (categoryFilter === "all" || item.category === categoryFilter) &&
      (statusFilter === "all" || item.status === statusFilter) &&
      (urgencyFilter === "all" || urgencyFilter === "not_urgent"),
    );
    return list.sort((a, b) => {
      if (sort === "date-asc") return a.created_at.localeCompare(b.created_at);
      if (sort === "category") return a.category.localeCompare(b.category) || a.created_at.localeCompare(b.created_at);
      if (sort === "status") return a.status.localeCompare(b.status) || a.created_at.localeCompare(b.created_at);
      if (sort === "urgency") return 0;
      return b.created_at.localeCompare(a.created_at);
    });
  }, [categoryFilter, data, sort, statusFilter, urgencyFilter]);

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
          <p className="mt-1 text-slate-600">Case activity by filing date · Singapore time</p>
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
                  {chartKeys(chartData).map((key, index) => <Line key={key} type="monotone" dataKey={key} name={dimensionValueLabel(dimension, key)} stroke={COLORS[index % COLORS.length]} strokeWidth={2} dot={false} />)}
                </LineChart>
              </ResponsiveContainer>
            </div>
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
                <PieChart><Pie data={data.breakdown.slices} dataKey="count" nameKey="label" cx="50%" cy="50%" outerRadius={86} label={({ name, value }) => `${name}: ${value}`}>
                  {data.breakdown.slices.map((slice, index) => <Cell key={slice.key} fill={COLORS[index % COLORS.length]} />)}
                </Pie><Tooltip /><Legend /></PieChart>
              </ResponsiveContainer>
            </div>
          </article>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><h2 className="text-lg font-semibold">Cases</h2><p className="text-sm text-slate-600">{visibleCases.length} shown · urgency is currently not urgent for every case</p></div>
              <div className="flex flex-wrap gap-2">
                <label className="sr-only" htmlFor="filter-category">Filter category</label><select id="filter-category" aria-label="Filter by category" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)} className="rounded border border-slate-300 px-2 py-2 text-sm"><option value="all">All categories</option>{allCategories().map((category) => <option key={category} value={category}>{labelForCategory(category)}</option>)}</select>
                <label className="sr-only" htmlFor="filter-status">Filter status</label><select id="filter-status" aria-label="Filter by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="rounded border border-slate-300 px-2 py-2 text-sm"><option value="all">All statuses</option>{(["queued", "resolved", "escalated", "pending_review", "overridden"] as CaseStatus[]).map((status) => <option key={status} value={status}>{labelForCaseStatus(status)}</option>)}</select>
                <label className="sr-only" htmlFor="filter-urgency">Filter urgency</label><select id="filter-urgency" aria-label="Filter by urgency" value={urgencyFilter} onChange={(event) => setUrgencyFilter(event.target.value)} className="rounded border border-slate-300 px-2 py-2 text-sm"><option value="all">All urgency</option><option value="not_urgent">Not urgent</option></select>
                <label className="sr-only" htmlFor="sort-cases">Sort cases</label><select id="sort-cases" aria-label="Sort cases" value={sort} onChange={(event) => setSort(event.target.value)} className="rounded border border-slate-300 px-2 py-2 text-sm"><option value="date-desc">Newest filed</option><option value="date-asc">Oldest filed</option><option value="category">Category</option><option value="status">Status</option><option value="urgency">Urgency</option></select>
              </div>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[780px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3">Case</th><th className="px-4 py-3">Category</th><th className="px-4 py-3">Filed</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Urgency</th><th className="px-4 py-3">Provider</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {visibleCases.map((item) => {
                  const caseLabel = <Link className="font-semibold text-teal-800 hover:underline" href={`/cases/${encodeURIComponent(item.case_id)}`}>{item.case_id}</Link>;
                  return <tr key={item.case_id} className="hover:bg-slate-50"><td className="px-5 py-4">{caseLabel}<div className="text-xs text-slate-500">{item.ride_id} · filed by {item.filed_by}</div></td><td className="px-4 py-4">{labelForCategory(item.category)}</td><td className="px-4 py-4">{new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore" }).format(new Date(item.created_at))}</td><td className="px-4 py-4">{labelForCaseStatus(item.status)}</td><td className="px-4 py-4">Not urgent</td><td className="px-4 py-4">{item.provider ?? "Not available"}</td></tr>;
                })}
                {visibleCases.length === 0 && <tr><td colSpan={6} className="px-5 py-10 text-center text-slate-500">No cases match these filters.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      </>}
    </main>
  );
}

async function loadAllCases(range: DateRange): Promise<CaseSummary[]> {
  const client = getActiveClient();
  const items: CaseSummary[] = [];
  let cursor: string | undefined;
  do {
    const page = await client.listDisputes({
      from: singaporeBoundary(range.from),
      to: singaporeBoundary(range.to, true),
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
