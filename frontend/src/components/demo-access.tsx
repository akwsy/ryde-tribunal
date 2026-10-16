"use client";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { getClient } from "@/lib/api/client";
import { clearDemoProfile, setDemoProfile } from "@/lib/demo-session";

export function DemoAccess({ children }: { children: ReactNode }) {
  const enabled = process.env.NEXT_PUBLIC_DEMO_ACCESS === "true";
  const [checking, setChecking] = useState(enabled);
  const [authenticated, setAuthenticated] = useState(!enabled);
  const [passcode, setPasscode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [profile, setProfile] = useState<string | null>(null);
  async function check() {
    setChecking(true); setError("");
    try { const value = await getClient().getDemoSession(); setAuthenticated(value.authenticated); setProfile(value.profile ?? null); setDemoProfile(value.mode === "guest" ? "guest" : "reviewer", value.profile); }
    catch { setError("The demo server may be starting. Wait a moment, then retry the connection."); }
    finally { setChecking(false); }
  }
  useEffect(() => {
    if (!enabled) return;
    void check();
    const expire = () => { setAuthenticated(false); setPasscode(""); setProfile(null); clearDemoProfile(); };
    window.addEventListener("ryde-session-expired", expire);
    return () => window.removeEventListener("ryde-session-expired", expire);
  // Check once at workspace entry; do not keep a free server awake in the background.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);
  async function signIn(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { const value = await getClient().signInDemo(passcode); setAuthenticated(value.authenticated); setProfile(value.profile ?? null); setDemoProfile("reviewer", value.profile); setPasscode(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not sign in."); }
    finally { setBusy(false); }
  }
  async function enterGuest(selected: "reviewer-preview" | "evidence-explorer") {
    setBusy(true); setError("");
    try { const value = await getClient().createGuestDemoSession(selected); setAuthenticated(value.authenticated); setProfile(value.profile ?? selected); setDemoProfile("guest", value.profile ?? selected); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not open the guest profile."); }
    finally { setBusy(false); }
  }
  if (!enabled) return <>{children}</>;
  if (authenticated) return <><div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-6 py-3 text-xs text-slate-700"><span>{profile === "reviewer-preview" ? "Guest profile · Reviewer preview" : profile === "evidence-explorer" ? "Guest profile · Evidence explorer" : "Judge reviewer"} · Synthetic records · {profile === "reviewer-preview" || profile === "evidence-explorer" ? "Read-only; actions are not saved" : "Financial actions are recommendations only"}</span><button className="font-semibold text-teal-800" onClick={async () => { await getClient().signOutDemo(); setAuthenticated(false); setProfile(null); clearDemoProfile(); }}>Exit profile</button></div>{children}</>;
  return <main className="mx-auto my-14 max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
    <p className="text-xs font-semibold uppercase tracking-wider text-teal-800">Ryde Tribunal</p><h1 className="mt-3 text-2xl font-semibold text-slate-900">Judge access</h1>
    <p className="mt-3 text-sm leading-relaxed text-slate-600">Choose a read-only guest profile to explore synthetic cases. Guest profiles cannot save changes. Reviewer access requires the judge passcode.</p>
    <div className="mt-6 grid gap-3">
      <button type="button" disabled={checking || busy} onClick={() => void enterGuest("reviewer-preview")} className="rounded-lg border border-teal-200 bg-teal-50 p-4 text-left hover:bg-teal-100 disabled:opacity-60"><span className="block font-semibold text-teal-950">Explore as a reviewer</span><span className="mt-1 block text-xs text-teal-900">Browse cases, decisions, and the review experience. Read-only.</span></button>
      <button type="button" disabled={checking || busy} onClick={() => void enterGuest("evidence-explorer")} className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-left hover:bg-slate-100 disabled:opacity-60"><span className="block font-semibold text-slate-900">Explore the evidence</span><span className="mt-1 block text-xs text-slate-700">Open sample case evidence and policy details. Read-only.</span></button>
    </div>
    <div className="my-6 flex items-center gap-3 text-xs text-slate-400"><span className="h-px flex-1 bg-slate-200" />Judge access<span className="h-px flex-1 bg-slate-200" /></div>
    {checking ? <p className="mt-6 text-sm text-teal-800" role="status">Connecting to the demo server… The first visit may take a moment.</p> : <form onSubmit={signIn} className="mt-6 space-y-4">
      <label className="block text-sm font-medium text-slate-800">Judge passcode<input type="password" autoComplete="current-password" required maxLength={256} value={passcode} onChange={event => setPasscode(event.target.value)} className="mt-2 block w-full rounded-lg border border-slate-300 p-3" /></label>
      <button disabled={busy} className="w-full rounded-lg bg-teal-700 px-4 py-3 text-sm font-semibold text-white disabled:opacity-60">{busy ? "Signing in…" : "Open reviewer workspace"}</button>
    </form>}
    {error && <div className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900" role="alert"><p>{error}</p><button type="button" onClick={() => void check()} className="mt-2 font-semibold underline">Retry connection</button></div>}
  </main>;
}
