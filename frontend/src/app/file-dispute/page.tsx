"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { getActiveClient } from "@/lib/api/fixture-client";
import type { Category, FileDisputeResponse, TripSearchPage } from "@/lib/api/types";
import { labelForCategory } from "@/lib/api/format";
import { isGuestDemo } from "@/lib/demo-session";

const CATEGORIES: Category[] = ["route_deviation", "no_show_charge", "fare_calculation", "other_cancellation_fee", "property_damage", "safety_incident", "lost_item", "conduct_complaint"];

export default function SimulatedFilingPage() {
  const guest = isGuestDemo();
  const [query, setQuery] = useState("");
  const [trips, setTrips] = useState<TripSearchPage["items"]>([]);
  const [selectedTrip, setSelectedTrip] = useState<TripSearchPage["items"][number] | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [filedBy, setFiledBy] = useState<"rider" | "driver">("rider");
  const [category, setCategory] = useState<Category>("route_deviation");
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [claimedAmount, setClaimedAmount] = useState("");
  const [categoryDetails, setCategoryDetails] = useState<Record<string, string>>({});
  const [attachments, setAttachments] = useState<File[]>([]);
  const filingInFlight = useRef(false);
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
    if (guest) { setError("Guest profiles can preview the filing form, but cannot submit or save a case."); return; }
    if (filingInFlight.current) return;
    if (!selectedTrip) {
      setError("Pick a trip in the database list before filing.");
      return;
    }
    filingInFlight.current = true;
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
        category_details: Object.fromEntries(Object.entries(categoryDetails).filter(([, value]) => value.trim())),
        attachments: await Promise.all(attachments.map(async (file) => ({
          file_name: file.name,
          media_type: file.type as "application/pdf" | "image/jpeg" | "image/png",
          data_base64: await fileToBase64(file),
        }))),
        ...(claimedAmount.trim() ? { claimed_amount: { amount_cents: Math.round(Number(claimedAmount) * 100), currency: "SGD" } } : {}),
      };
      if (claimedAmount.trim() && (!Number.isFinite(Number(claimedAmount)) || Number(claimedAmount) <= 0)) {
        throw new Error("Enter a positive claimed amount, or leave it blank.");
      }
      const response = await getActiveClient().fileDispute(body, crypto.randomUUID());
      setResult(response);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Dispute could not be filed.");
    } finally {
      filingInFlight.current = false;
      setSubmitting(false);
    }
  }

  return <main className="mx-auto max-w-3xl px-5 py-8 text-slate-900 sm:px-8">
    <Link href="/" className="text-sm font-medium text-teal-800 hover:underline">← Reviewer dashboard</Link>
    <header className="mb-7 mt-5"><p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-700">Simulation tool</p><h1 className="mt-2 text-3xl font-bold">File a dispute</h1><p className="mt-2 text-slate-600">This form simulates a rider or driver filing against a trip already in the database.</p></header>
    {result && <div role="status" className="mb-5 rounded-lg border border-green-200 bg-green-50 p-4 text-green-900">Dispute filed. Open the case to start adjudication: <Link className="font-semibold underline" href={`/cases/${encodeURIComponent(result.case_id)}`}>{result.case_id}</Link> · {result.status}</div>}
    {error && <p role="alert" className="mb-5 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{error}</p>}
    {guest && <p className="mb-4 rounded-lg border border-sky-200 bg-sky-50 p-4 text-sm text-sky-950">Guest preview: explore the filing questions, but saving is turned off. No case or attachment will be sent or stored.</p>}
    <form onSubmit={submit} className="space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <label className="block text-sm font-medium">Filed by
        <select value={filedBy} onChange={(event) => setFiledBy(event.target.value as "rider" | "driver")} className="mt-1 block w-full rounded border border-slate-300 px-3 py-2"><option value="rider">Rider</option><option value="driver">Driver</option></select>
      </label>
      <label className="block text-sm font-medium">Dispute category
        <select value={category} onChange={(event) => { setCategory(event.target.value as Category); setCategoryDetails({}); }} className="mt-1 block w-full rounded border border-slate-300 px-3 py-2">{CATEGORIES.map((item) => <option key={item} value={item}>{labelForCategory(item)}</option>)}</select>
      </label>
      <CategoryQuestions category={category} values={categoryDetails} onChange={(key, value) => setCategoryDetails((current) => ({ ...current, [key]: value }))} />
      <p className="-mt-3 rounded-md bg-teal-50 p-3 text-sm text-teal-900">
        {category === "fare_calculation" || category === "other_cancellation_fee"
          ? "Verified trip and payment records may support an automatic decision. Missing or conflicting records go to a reviewer."
          : category === "route_deviation" || category === "no_show_charge"
            ? "Clear cases can be decided automatically; uncertain cases go to a reviewer."
            : "The app will organise evidence and urgency automatically. A human reviewer makes the final decision for this category."}
      </p>
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
      <label className="block text-sm font-medium">Supporting documents <span className="font-normal text-slate-500">(optional, PDF/JPEG/PNG)</span>
        <input type="file" accept="application/pdf,image/jpeg,image/png" multiple onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          const total = files.reduce((sum, file) => sum + file.size, 0);
          if (files.length > 5 || files.some((file) => !["application/pdf", "image/jpeg", "image/png"].includes(file.type) || file.size > 4 * 1024 * 1024) || total > 8 * 1024 * 1024) {
            setError("Choose up to five PDF, JPEG, or PNG files. Each must be 4 MB or smaller, with 8 MB total.");
            event.currentTarget.value = "";
            setAttachments([]);
            return;
          }
          setError(null); setAttachments(files);
        }} className="mt-1 block w-full rounded border border-slate-300 px-3 py-2" />
        {attachments.length > 0 && <span className="mt-1 block text-xs font-normal text-slate-600">{attachments.map((file) => file.name).join(", ")} · submitted files are unverified until a reviewer checks them</span>}
      </label>
      <button type="submit" disabled={guest || submitting || !selectedTrip} className="rounded-md bg-teal-700 px-5 py-2.5 font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50">{guest ? "Guest preview · filing disabled" : submitting ? "Filing…" : "File dispute"}</button>
    </form>
  </main>;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.onload = () => {
      const result = String(reader.result ?? "");
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}

function CategoryQuestions({ category, values, onChange }: {
  category: Category;
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
}) {
  const fields: Record<Category, Array<[string, string, string]>> = {
    route_deviation: [], no_show_charge: [],
    fare_calculation: [["disputed_component", "Which fare item is disputed?", "e.g. toll, platform fee, base fare"]],
    other_cancellation_fee: [["fee_type", "Which charge or payout?", "cancellation, waiting, or driver payout"], ["event_timing", "What timing do you dispute?", "When the cancellation or wait happened"]],
    property_damage: [["damage_description", "What was damaged or cleaned?", "Describe the item or cleaning claim"], ["claim_type", "Type of cleaning claim", "minor_spillage, stains_or_bodily_fluids, or vomit"], ["claim_amount_cents", "Claim amount in cents", "Enter the amount shown on the receipt"], ["incident_timing", "When was it noticed?", "Date and approximate time"]],
    safety_incident: [["incident_type", "What needs urgent attention?", "Describe the safety concern"], ["incident_timing", "When did it happen?", "Date and approximate time"]],
    lost_item: [["item_description", "What item was lost?", "Colour, brand, or other identifying details"], ["last_known_location", "Where was it last seen?", "Pickup, vehicle, or drop-off"], ["reported_item_status", "Reported status", "reported, found, returned, or unresolved"]],
    conduct_complaint: [["conduct_type", "What conduct are you reporting?", "Briefly describe the concern"], ["incident_timing", "When did it happen?", "Date and approximate time"]],
  };
  const categoryFields = fields[category];
  const choices: Record<string, string[]> = {
    fee_type: ["rider_cancellation", "rider_waiting", "driver_payout"],
    claim_type: ["minor_spillage", "stains_or_bodily_fluids", "vomit"],
    reported_item_status: ["reported", "found", "returned", "unresolved"],
  };
  if (!categoryFields.length) return null;
  return <fieldset className="space-y-3 rounded-lg border border-slate-200 p-4">
    <legend className="px-1 text-sm font-semibold">Details for this dispute</legend>
    {categoryFields.map(([key, label, placeholder]) => <label key={key} className="block text-sm font-medium">{label}
      {choices[key] ? <select value={values[key] ?? ""} onChange={(event) => onChange(key, event.target.value)} className="mt-1 block w-full rounded border border-slate-300 px-3 py-2"><option value="">Choose an option</option>{choices[key].map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select>
        : <input value={values[key] ?? ""} onChange={(event) => onChange(key, event.target.value)} maxLength={500} placeholder={placeholder} className="mt-1 block w-full rounded border border-slate-300 px-3 py-2" />}
    </label>)}
  </fieldset>;
}

function Detail({ label, value }: { label: string; value: string | null }) {
  return <div><dt className="inline text-slate-500">{label}: </dt><dd className="inline">{value ?? "Not available"}</dd></div>;
}
