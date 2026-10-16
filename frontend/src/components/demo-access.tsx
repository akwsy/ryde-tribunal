"use client";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { getClient } from "@/lib/api/client";

export function DemoAccess({ children }: { children: ReactNode }) {
  const enabled = process.env.NEXT_PUBLIC_DEMO_ACCESS === "true";
  const [checking, setChecking] = useState(enabled);
  const [authenticated, setAuthenticated] = useState(!enabled);
  const [passcode, setPasscode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function check() {
    setChecking(true); setError("");
    try { const value = await getClient().getDemoSession(); setAuthenticated(value.authenticated); }
    catch { setError("The demo server may be starting. Wait a moment, then retry the connection."); }
    finally { setChecking(false); }
  }
  useEffect(() => {
    if (!enabled) return;
    void check();
    const expire = () => { setAuthenticated(false); setPasscode(""); };
    window.addEventListener("ryde-session-expired", expire);
    return () => window.removeEventListener("ryde-session-expired", expire);
  // Check once at workspace entry; do not keep a free server awake in the background.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);
  async function signIn(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { const value = await getClient().signInDemo(passcode); setAuthenticated(value.authenticated); setPasscode(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not sign in."); }
    finally { setBusy(false); }
  }
  if (!enabled) return <>{children}</>;
  if (authenticated) return <><div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-3 text-xs text-slate-600"><span>Judge demo · All records are synthetic · No financial actions are executed</span><button className="font-semibold text-teal-800" onClick={async () => { await getClient().signOutDemo(); setAuthenticated(false); }}>Sign out</button></div>{children}</>;
  return <main className="mx-auto my-14 max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
    <p className="text-xs font-semibold uppercase tracking-wider text-teal-800">Ryde Tribunal</p><h1 className="mt-3 text-2xl font-semibold text-slate-900">Judge access</h1>
    <p className="mt-3 text-sm leading-relaxed text-slate-600">Enter the passcode supplied with the submission to explore the working app using synthetic disputes.</p>
    {checking ? <p className="mt-6 text-sm text-teal-800" role="status">Connecting to the demo server… The first visit may take a moment.</p> : <form onSubmit={signIn} className="mt-6 space-y-4">
      <label className="block text-sm font-medium text-slate-800">Judge passcode<input type="password" autoComplete="current-password" required maxLength={256} value={passcode} onChange={event => setPasscode(event.target.value)} className="mt-2 block w-full rounded-lg border border-slate-300 p-3" /></label>
      <button disabled={busy} className="w-full rounded-lg bg-teal-700 px-4 py-3 text-sm font-semibold text-white disabled:opacity-60">{busy ? "Signing in…" : "Open reviewer workspace"}</button>
    </form>}
    {error && <div className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900" role="alert"><p>{error}</p><button type="button" onClick={() => void check()} className="mt-2 font-semibold underline">Retry connection</button></div>}
  </main>;
}
