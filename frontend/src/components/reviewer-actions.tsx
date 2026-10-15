"use client";

import { useState, type FormEvent } from "react";
import { getActiveClient } from "@/lib/api/fixture-client";
import type { CaseResult, ReasonCode, RulingType } from "@/lib/api/types";

const reasonCodes: { value: ReasonCode; label: string }[] = [
  { value: "policy_misapplied", label: "Policy misapplied" },
  { value: "evidence_misweighted", label: "Evidence misweighted" },
  { value: "evidence_missing", label: "Evidence missing" },
  { value: "fraud_suspected", label: "Fraud suspected" },
  { value: "goodwill", label: "Goodwill" },
  { value: "safety_override", label: "Safety override" },
  { value: "other", label: "Other" },
];

const rulingTypes: { value: RulingType; label: string }[] = [
  { value: "refund", label: "Refund" },
  { value: "compensation", label: "Compensation" },
  { value: "no_action", label: "No action" },
];

export function ReviewerActions({
  caseResult,
  onUpdated,
}: {
  caseResult: CaseResult;
  onUpdated: (result: CaseResult) => void;
}) {
  const [approvalNote, setApprovalNote] = useState("");
  const [rulingType, setRulingType] = useState<RulingType>("no_action");
  const [delivery, setDelivery] = useState<"voucher" | "none" | "unspecified">("unspecified");
  const [description, setDescription] = useState("");
  const [reasonCode, setReasonCode] = useState<ReasonCode>("other");
  const [rationale, setRationale] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("SGD");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!caseResult.judge) return null;

  const approve = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const updated = await getActiveClient().approveResolution(caseResult.case_id, approvalNote || undefined);
      onUpdated(updated);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not approve this ruling.");
    } finally {
      setBusy(false);
    }
  };

  const override = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const numericAmount = amount.trim() === "" ? undefined : Number(amount);
    if (numericAmount !== undefined && !Number.isFinite(numericAmount)) {
      setError("Enter a valid amount.");
      setBusy(false);
      return;
    }
    try {
      const updated = await getActiveClient().overrideResolution(caseResult.case_id, {
        ruling_type: rulingType,
        recommended_action: {
          description: description.trim(),
          delivery,
          ...(numericAmount === undefined ? {} : {
            amount: { amount_cents: Math.round(numericAmount * 100), currency: currency.trim().toUpperCase() },
          }),
        },
        reason_code: reasonCode,
        rationale: rationale.trim(),
      });
      onUpdated(updated);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save this override.");
    } finally {
      setBusy(false);
    }
  };

  const canOverride = caseResult.status === "resolved" || caseResult.status === "overridden" || caseResult.status === "escalated";
  const canApprove = caseResult.reviewer_approved_ruling === null;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5" aria-label="Reviewer actions" data-testid="reviewer-actions">
      <h2 className="text-lg font-bold text-slate-900">Reviewer decision</h2>
      <p className="mt-1 text-sm text-slate-600">The model’s proposal remains recorded separately from your decision.</p>

      {error && <p className="mt-3 rounded-md bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}

      {canApprove && (
        <form onSubmit={approve} className="mt-4 rounded-lg border border-green-200 bg-green-50 p-4" aria-label="Approve model ruling">
          <h3 className="font-semibold text-green-950">Approve proposed ruling</h3>
          <label className="mt-3 block text-sm font-medium text-slate-800" htmlFor="approval-note">Approval note <span className="font-normal text-slate-500">(optional)</span></label>
          <textarea id="approval-note" maxLength={2000} value={approvalNote} onChange={(event) => setApprovalNote(event.target.value)} rows={3} className="mt-1 w-full rounded-md border border-slate-300 bg-white p-2 text-sm" />
          <button type="submit" disabled={busy} className="mt-3 rounded-md bg-green-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">{busy ? "Saving…" : "Approve ruling"}</button>
        </form>
      )}

      {canOverride && (
        <form onSubmit={override} className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4" aria-label="Override ruling">
          <h3 className="font-semibold text-amber-950">Override ruling</h3>
          <p className="mt-1 text-sm text-amber-900">The original model ruling stays in the case history.</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="block text-sm font-medium text-slate-800">Ruling type
              <select required value={rulingType} onChange={(event) => setRulingType(event.target.value as RulingType)} className="mt-1 block w-full rounded-md border border-slate-300 bg-white p-2">
                {rulingTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </label>
            <label className="block text-sm font-medium text-slate-800">Reason code
              <select required value={reasonCode} onChange={(event) => setReasonCode(event.target.value as ReasonCode)} className="mt-1 block w-full rounded-md border border-slate-300 bg-white p-2">
                {reasonCodes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </label>
          </div>
          <label className="mt-3 block text-sm font-medium">Remedy delivery<select aria-label="Remedy delivery" value={delivery} onChange={event => setDelivery(event.target.value as typeof delivery)} className="mt-1 block w-full rounded-md border border-slate-300 bg-white p-2"><option value="unspecified">Unspecified recommendation</option><option value="voucher">Voucher waiver</option><option value="none">No monetary delivery</option></select></label>
          <label className="mt-3 block text-sm font-medium text-slate-800" htmlFor="override-description">Recommended action</label>
          <textarea id="override-description" required value={description} onChange={(event) => setDescription(event.target.value)} rows={2} className="mt-1 w-full rounded-md border border-slate-300 bg-white p-2 text-sm" />
          <fieldset className="mt-3 grid gap-3 sm:grid-cols-[1fr_8rem]">
            <label className="block text-sm font-medium text-slate-800">Award amount <span className="font-normal text-slate-500">(optional, in dollars)</span>
              <input type="number" step="0.01" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} className="mt-1 block w-full rounded-md border border-slate-300 bg-white p-2" />
            </label>
            <label className="block text-sm font-medium text-slate-800">Currency
              <input required={amount.trim() !== ""} minLength={3} maxLength={3} value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} className="mt-1 block w-full rounded-md border border-slate-300 bg-white p-2 uppercase" />
            </label>
          </fieldset>
          <label className="mt-3 block text-sm font-medium text-slate-800" htmlFor="override-rationale">Rationale</label>
          <textarea id="override-rationale" required minLength={1} maxLength={5000} value={rationale} onChange={(event) => setRationale(event.target.value)} rows={4} className="mt-1 w-full rounded-md border border-slate-300 bg-white p-2 text-sm" />
          <button type="submit" disabled={busy} className="mt-3 rounded-md bg-amber-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">{busy ? "Saving…" : "Save override"}</button>
        </form>
      )}
    </section>
  );
}
