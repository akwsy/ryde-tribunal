"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getActiveClient } from "@/lib/api/fixture-client";
import type { Category, FileDisputeResponse, TripSearchPage } from "@/lib/api/types";
import { labelForCategory } from "@/lib/api/format";

const CATEGORIES: Category[] = ["route_deviation", "no_show_charge", "fare_calculation", "other_cancellation_fee", "property_damage", "safety_incident", "lost_item", "conduct_complaint"];

export default function SimulatedFilingPage() {
  const [query, setQuery] = useState("");
  const [trips, setTrips] = useState<TripSearchPage["items"]>([]);
  const [selectedTrip, setSelectedTrip] = useState<TripSearchPage["items"][number] | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [filedBy, setFiledBy] = useState<"rider" | "driver">("rider");
  const [category, setCategory] = useState<Category>("route_deviation");
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [claimedAmount, setClaimedAmount] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FileDisputeResponse | null>(null);

  useEffect(() => {
    if (!pickerOpen) return;
    const timer = window.setTimeout(() => {
      void getActiveClient().searchTrips(query, 20)
        .then((page) => setTrips(page.items))
        .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Could not search trips."));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [pickerOpen, query]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedTrip) {
      setError("Pick a trip in the database list before filing.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const body = {
        category,
        ride_id: selectedTrip.ride_id,
        filed_by: filedBy,
        subject,
        description,
        ...(claimedAmount.trim() ? { claimed_amount: { amount_cents: Math.round(Number(claimedAmount) * 100), currency: "SGD" } } : {}),
      };
      if (claimedAmount.trim() && (!Number.isFinite(Number(claimedAmount)) || Number(claimedAmount) <= 0)) {
        throw new Error("Enter a positive claimed amount, or leave it blank.");
      }
      const response = await getActiveClient().fileDispute(body);
      setResult(response);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Dispute could not be filed.");
    } finally {
      setSubmitting(false);
    }
  }

  return <main className="mx-auto max-w-3xl px-5 py-8 text-slate-900 sm:px-8">
    <Link href="/" className="text-sm font-medium text-teal-800 hover:underline">← Reviewer dashboard</Link>
    <header className="mb-7 mt-5"><p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">Simulation tool</p><h1 className="mt-2 text-3xl font-bold">File a dispute</h1><p className="mt-2 text-slate-600">This form simulates a rider or driver filing against a trip already in the database.</p></header>
    {result && <div role="status" className="mb-5 rounded-lg border border-green-200 bg-green-50 p-4 text-green-900">Dispute filed: <Link className="font-semibold underline" href={`/cases/${encodeURIComponent(result.case_id)}`}>{result.case_id}</Link> · {result.status}</div>}
    {error && <p role="alert" className="mb-5 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{error}</p>}
    <form onSubmit={submit} className="space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <label className="block text-sm font-medium">Filed by
        <select value={filedBy} onChange={(event) => setFiledBy(event.target.value as "rider" | "driver")} className="mt-1 block w-full rounded border border-slate-300 px-3 py-2"><option value="rider">Rider</option><option value="driver">Driver</option></select>
      </label>
      <label className="block text-sm font-medium">Dispute category
        <select value={category} onChange={(event) => setCategory(event.target.value as Category)} className="mt-1 block w-full rounded border border-slate-300 px-3 py-2">{CATEGORIES.map((item) => <option key={item} value={item}>{labelForCategory(item)}</option>)}</select>
      </label>
      <div className="relative">
        <label htmlFor="trip-search" className="block text-sm font-medium">Trip in the database</label>
        <input id="trip-search" role="combobox" aria-expanded={pickerOpen} aria-controls="trip-options" aria-autocomplete="list" autoComplete="off" value={selectedTrip ? `${selectedTrip.ride_id} — ${selectedTrip.pickup_label ?? "Unknown pickup"} to ${selectedTrip.dropoff_label ?? "Unknown drop-off"}` : query}
          onFocus={() => { setSelectedTrip(null); setPickerOpen(true); setQuery(""); }} onChange={(event) => { setSelectedTrip(null); setQuery(event.target.value); setPickerOpen(true); }} placeholder="Click to search internal trip IDs and locations" className="mt-1 block w-full rounded border border-slate-300 px-3 py-2" />
        {pickerOpen && <div id="trip-options" role="listbox" className="absolute z-10 mt-1 max-h-64 w-full overflow-y-auto rounded border border-slate-300 bg-white shadow-lg">
          {trips.map((trip) => <button key={trip.ride_id} type="button" role="option" aria-selected={selectedTrip?.ride_id === trip.ride_id} onClick={() => { setSelectedTrip(trip); setQuery(""); setPickerOpen(false); setError(null); }} className="block w-full border-b border-slate-100 px-4 py-3 text-left last:border-0 hover:bg-teal-50">
            <span className="block font-semibold">{trip.ride_id} · {trip.pickup_label ?? "Unknown pickup"} → {trip.dropoff_label ?? "Unknown drop-off"}</span><span className="text-xs text-slate-600">{trip.booked_at ? new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore" }).format(new Date(trip.booked_at)) : "Date unavailable"} · {trip.status ?? "Status unavailable"}</span>
          </button>)}
          {trips.length === 0 && <p className="p-4 text-sm text-slate-600">No matching trips found.</p>}
        </div>}
      </div>
      {selectedTrip && <section aria-label="Selected trip details" className="rounded-lg bg-slate-50 p-4 text-sm"><h2 className="font-semibold">Selected trip: {selectedTrip.ride_id}</h2><dl className="mt-2 grid gap-x-5 gap-y-1 sm:grid-cols-2"><Detail label="Pickup" value={selectedTrip.pickup_label} /><Detail label="Drop-off" value={selectedTrip.dropoff_label} /><Detail label="Rider" value={selectedTrip.rider_name} /><Detail label="Driver" value={selectedTrip.driver_name} /><Detail label="Trip status" value={selectedTrip.status} /><Detail label="Booked" value={selectedTrip.booked_at ? new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore" }).format(new Date(selectedTrip.booked_at)) : null} /></dl></section>}
      <label className="block text-sm font-medium">Subject<input required maxLength={200} value={subject} onChange={(event) => setSubject(event.target.value)} className="mt-1 block w-full rounded border border-slate-300 px-3 py-2" /></label>
      <label className="block text-sm font-medium">Description<textarea required maxLength={5000} rows={5} value={description} onChange={(event) => setDescription(event.target.value)} className="mt-1 block w-full rounded border border-slate-300 px-3 py-2" /></label>
      <label className="block text-sm font-medium">Claimed amount in SGD <span className="font-normal text-slate-500">(optional)</span><input inputMode="decimal" type="number" min="0.01" step="0.01" value={claimedAmount} onChange={(event) => setClaimedAmount(event.target.value)} className="mt-1 block w-full rounded border border-slate-300 px-3 py-2" /></label>
      <button type="submit" disabled={submitting || !selectedTrip} className="rounded-md bg-teal-700 px-5 py-2.5 font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50">{submitting ? "Filing…" : "File dispute"}</button>
    </form>
  </main>;
}

function Detail({ label, value }: { label: string; value: string | null }) {
  return <div><dt className="inline text-slate-500">{label}: </dt><dd className="inline">{value ?? "Not available"}</dd></div>;
}
