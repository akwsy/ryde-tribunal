"use client";

import Link from "next/link";
import { useState } from "react";
import { getActiveClient } from "@/lib/api/fixture-client";
import type { ImportResult } from "@/lib/api/types";

export default function ImportCompanyDataPage() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fixtureMode = !(typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResult(null);
    if (!file || !file.name.toLowerCase().endsWith(".zip")) {
      setError("Choose a ZIP archive of related CSV files.");
      return;
    }
    setBusy(true);
    try {
      setResult(await getActiveClient().importCompanyData(file));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The import failed.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="mx-auto max-w-3xl px-5 py-8 text-slate-900 sm:px-8">
    <Link href="/" className="text-sm font-medium text-teal-800 hover:underline">← Reviewer dashboard</Link>
    <header className="mb-7 mt-5"><p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">Company data</p><h1 className="mt-2 text-3xl font-bold">Import a CSV bundle</h1><p className="mt-2 text-slate-600">Upload one ZIP containing the related CSV files. The server checks the archive before writing; rows with existing company IDs are skipped.</p></header>
    {fixtureMode && <p className="mb-5 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><strong>Fixture mode:</strong> the dashboard is not connected to the database. This page will not write company data. Set the local API URL to use a live backend.</p>}
    {error && <p role="alert" className="mb-5 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{error}</p>}
    {result && <section role="status" className="mb-5 rounded-lg border border-green-200 bg-green-50 p-5 text-green-950"><h2 className="font-semibold">Import completed</h2><p className="mt-1 text-sm">Source: {result.source_system}</p><div className="mt-4 grid gap-4 sm:grid-cols-2"><CountGroup title="Imported" counts={result.imported} /><CountGroup title="Skipped: duplicate company IDs" counts={result.skipped_duplicate_ids} /></div></section>}
    <form onSubmit={submit} className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <label className="block text-sm font-medium">ZIP file<input type="file" accept=".zip,application/zip" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setResult(null); }} className="mt-2 block w-full rounded border border-slate-300 px-3 py-2 file:mr-3 file:rounded file:border-0 file:bg-slate-100 file:px-3 file:py-1.5" /></label>
      {file && <p className="mt-2 text-sm text-slate-600">Selected: {file.name} ({(file.size / 1024).toFixed(1)} KB)</p>}
      <button type="submit" disabled={!file || busy || fixtureMode} className="mt-5 rounded-md bg-teal-700 px-5 py-2.5 font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50">{busy ? "Importing…" : "Import ZIP"}</button>
      <p className="mt-3 text-xs text-slate-500">The import appends new trip, profile, and evidence rows. It does not import dispute tickets or policy. Imported records stay in the local database and are not added to this repository.</p>
    </form>
    <details className="mt-5 rounded-lg border border-slate-200 bg-white p-4 text-sm"><summary className="cursor-pointer font-medium">Required archive contents</summary><p className="mt-3 text-slate-600">At the ZIP root: manifest.json, users.csv, profiles.csv, trips.csv, gps_telemetry.csv, chat_logs.csv, and app_events.csv. evidence_metadata.csv is optional. The manifest must contain format_version &quot;1&quot; and a stable source_system name. All headers and row references are validated before writing.</p><p className="mt-2 text-slate-600">Use the exact column headers from <code>database/importer/FORMAT.md</code>. Existing company IDs are skipped without changing their stored content.</p></details>
  </main>;
}

function CountGroup({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  return <div><h3 className="text-sm font-semibold">{title}</h3>{entries.length ? <ul className="mt-1 text-sm">{entries.map(([name, count]) => <li key={name} className="flex justify-between gap-4"><span>{name.replaceAll("_", " ")}</span><span className="font-semibold tabular-nums">{count}</span></li>)}</ul> : <p className="mt-1 text-sm text-slate-600">0 records</p>}</div>;
}
