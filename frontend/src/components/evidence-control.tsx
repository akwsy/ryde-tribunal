"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { Evidence } from "@/lib/api/types";
import { labelForEvidenceClass, labelForVerificationStatus, formatDateTime } from "@/lib/api/format";
import { getActiveClient } from "@/lib/api/fixture-client";
import { ApiError } from "@/lib/api/client";

const EvidenceMap = dynamic(() => import("./evidence-map"), {
  ssr: false,
  loading: () => <div className="evidence-map-placeholder" role="status">Loading map…</div>,
});

type Point = { lat: number; lon: number };
type PanelPosition = { x: number; y: number };

export function EvidenceControl({
  evidenceId,
  caseId,
  title: cardTitle,
  initialEvidence,
  citedField,
  observedValue,
  summary,
}: {
  evidenceId: string;
  caseId: string;
  title?: string;
  initialEvidence?: Evidence;
  citedField?: string;
  observedValue?: unknown;
  summary?: string;
}) {
  const dialogId = `evidence-dialog-${useId().replaceAll(":", "")}`;
  const openerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const dragOrigin = useRef<{ pointerX: number; pointerY: number; x: number; y: number } | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(initialEvidence ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PanelPosition>({ x: 28, y: 76 });

  const close = useCallback(() => {
    setOpen(false);
    requestAnimationFrame(() => openerRef.current?.focus());
  }, []);

  const handleOpen = useCallback(async () => {
    openerRef.current = document.activeElement instanceof HTMLButtonElement ? document.activeElement : null;
    setError(null);
    setOpen(true);
    if (!evidence) {
      setLoading(true);
      try {
        setEvidence(await getActiveClient().getEvidence(evidenceId));
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : "Could not load this evidence record.");
      } finally {
        setLoading(false);
      }
    }
  }, [evidence, evidenceId]);

  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open, loading]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key === "Tab") {
        const dialog = document.getElementById(dialogId);
        const controls = dialog?.querySelectorAll<HTMLElement>("button:not([disabled]), a[href], summary, [tabindex='0']");
        if (!controls?.length) return;
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [close, dialogId, open]);

  function startDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (event.pointerType === "touch") return;
    dragOrigin.current = { pointerX: event.clientX, pointerY: event.clientY, ...position };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragOrigin.current) return;
    const start = dragOrigin.current;
    setPosition(clampPanelPosition({
      x: start.x + event.clientX - start.pointerX,
      y: start.y + event.clientY - start.pointerY,
    }));
  }

  function moveWithKeyboard(event: React.KeyboardEvent<HTMLDivElement>) {
    const shifts: Record<string, PanelPosition> = {
      ArrowLeft: { x: -24, y: 0 }, ArrowRight: { x: 24, y: 0 },
      ArrowUp: { x: 0, y: -24 }, ArrowDown: { x: 0, y: 24 },
    };
    const shift = shifts[event.key];
    if (!shift) return;
    event.preventDefault();
    setPosition(clampPanelPosition({ x: position.x + shift.x, y: position.y + shift.y }));
  }

  const title = cardTitle || evidenceLabel(evidence?.class);
  const humanSummary = summary || (evidence ? summarizeEvidence(evidence) : "Open the source record and see what it contains.");
  const mapPoints = evidence ? pointsForEvidence(evidence) : [];

  return (
    <div className="evidence-card" data-testid={`evidence-control-${evidenceId}`} data-case-id={caseId}>
      <div className="evidence-card-icon" aria-hidden="true">{iconForEvidence(evidence?.class, citedField)}</div>
      <div className="evidence-card-copy">
        <p className="evidence-card-title">{title}</p>
        <p className="evidence-card-summary">{humanSummary}</p>
        {citedField && <p className="evidence-card-context">{labelForField(citedField)}{observedValue !== undefined ? ` · ${formatObservedValue(citedField, observedValue)}` : ""}</p>}
      </div>
      <button
        type="button"
        ref={openerRef}
        onClick={handleOpen}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={dialogId}
        className="evidence-view-button"
      >
        View evidence
      </button>

      {open && <div className="evidence-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}>
        <section
          id={dialogId}
          className="evidence-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby={`${dialogId}-title`}
          data-testid={`evidence-detail-${evidenceId}`}
          style={{ left: position.x, top: position.y }}
        >
          <div className="evidence-dialog-header" onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={() => { dragOrigin.current = null; }} onPointerCancel={() => { dragOrigin.current = null; }} onKeyDown={moveWithKeyboard} tabIndex={0} aria-label="Move evidence panel with arrow keys">
            <div>
              <p className="evidence-dialog-eyebrow">Evidence record</p>
              <h2 id={`${dialogId}-title`}>{title}</h2>
            </div>
            <button ref={closeRef} type="button" onClick={close} className="evidence-close-button" aria-label="Close evidence">×</button>
          </div>
          <div className="evidence-dialog-body" aria-live="polite">
            {loading && <p role="status" className="evidence-state">Loading evidence…</p>}
            {error && <p role="alert" className="evidence-state evidence-error">{error}</p>}
            {evidence && <>
              <div className="evidence-summary-panel">
                <div className="evidence-summary-top"><span>{labelForEvidenceClass(evidence.class)}</span><VerificationBadge status={evidence.verification.status} uncertaintyPct={evidence.verification.uncertainty_pct} size="sm" /></div>
                <p>{summarizeEvidence(evidence)}</p>
                {citedField && <div className="evidence-cited-field"><strong>Used for this point</strong><span>{labelForField(citedField)}</span><b>{formatObservedValue(citedField, observedValue ?? readField(evidence.payload, citedField))}</b></div>}
              </div>
              {mapPoints.length > 0 && <EvidenceMap evidence={evidence} points={mapPoints} />}
              {evidence.class === "chat_log" && <ChatPreview evidence={evidence} />}
              {evidence.class === "fare" && <FarePreview evidence={evidence} />}
              {evidence.class === "attachment" && process.env.NEXT_PUBLIC_API_BASE_URL && <a className="inline-flex rounded-md bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800" href={`${process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/$/, "")}/evidence/${encodeURIComponent(evidenceId)}/download`}>Download original file</a>}
              <dl className="evidence-metadata">
                <div><dt>Recorded at</dt><dd>{formatDateTime(evidence.recorded_at)}</dd></div>
                <div><dt>Evidence source</dt><dd>{evidence.source.replaceAll("_", " ")}</dd></div>
                <div><dt>Visible to</dt><dd>{evidence.visibility.replaceAll("_", " ")}</dd></div>
                <div><dt>Evidence ID</dt><dd>{evidence.evidence_id}</dd></div>
              </dl>
              <details className="evidence-technical-details">
                <summary>Technical details</summary>
                <p className="evidence-detail-label">Provenance</p>
                <pre>{JSON.stringify(evidence.provenance, null, 2)}</pre>
                <p className="evidence-detail-label">Full source record</p>
                <pre>{JSON.stringify(evidence.payload, null, 2)}</pre>
              </details>
            </>}
          </div>
        </section>
      </div>}
    </div>
  );
}

function ChatPreview({ evidence }: { evidence: Evidence }) {
  const messages = arrayAt(evidence.payload, "messages");
  if (!messages.length) return null;
  return <section className="evidence-content-section" aria-label="Recorded messages">
    <h3>Messages</h3>
    <ol className="evidence-message-list">{messages.map((item, index) => {
      const message = asRecord(item);
      return <li key={index}><span>{humanize(String(message.role ?? "participant"))}</span><p>{String(message.text ?? message.message_text ?? "Message text unavailable")}</p><time>{message.timestamp || message.sent_at ? formatDateTime(String(message.timestamp ?? message.sent_at)) : "Time not recorded"}</time></li>;
    })}</ol>
  </section>;
}

function FarePreview({ evidence }: { evidence: Evidence }) {
  const payload = evidence.payload;
  const rows: Array<[string, unknown]> = [
    ["Quoted fare", payload.quoted_fare_cents], ["Charged fare", payload.charged_fare_cents],
    ["Cancellation fee", payload.cancellation_fee_cents], ["Waiting fee", payload.waiting_fare_cents],
  ].filter((entry) => entry[1] !== null && entry[1] !== undefined) as Array<[string, unknown]>;
  if (!rows.length) return null;
  return <section className="evidence-content-section" aria-label="Fare details"><h3>Fare details</h3><dl className="fare-list">{rows.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{formatObservedValue(`${name.toLowerCase().replaceAll(" ", "_")}_cents`, value)}</dd></div>)}</dl></section>;
}

function summarizeEvidence(evidence: Evidence): string {
  const payload = evidence.payload;
  if (evidence.class === "attachment") return `${String(payload.file_name ?? "Submitted document")} · submitted by a party and awaiting verification`;
  if (evidence.class === "gps_telemetry") {
    const route = asRecord(payload.route);
    const samples = arrayAt(payload, "samples").length || arrayAt(payload, "observed_samples").length;
    const planned = route.planned_distance_km ?? payload.planned_distance_km;
    const actual = route.actual_distance_km ?? payload.actual_distance_km;
    if (actual !== undefined && planned !== undefined) return `Trip route recorded · ${formatDistance(actual)} travelled, ${formatDistance(planned)} planned`;
    if (samples > 1) return `GPS trace with ${samples} recorded location points`;
    if (pointsForEvidence(evidence).length) return "Recorded GPS location available on the map";
    if (payload.min_distance_to_pickup_m !== undefined) return `Closest GPS point was ${formatObservedValue("min_distance_to_pickup_m", payload.min_distance_to_pickup_m)} from pickup`;
    return "GPS record · location details available in the source record";
  }
  if (evidence.class === "chat_log") {
    const count = arrayAt(payload, "messages").length || Number(payload.message_count ?? 0);
    return count ? `${count} recorded message${count === 1 ? "" : "s"}` : "Recorded trip messages";
  }
  if (evidence.class === "fare") {
    if (payload.charged_fare_cents !== undefined) return `Recorded charge ${formatMoney(payload.charged_fare_cents)}${payload.quoted_fare_cents !== undefined ? ` · quote ${formatMoney(payload.quoted_fare_cents)}` : ""}`;
    if (payload.cancellation_fee_cents !== undefined) return `Cancellation fee recorded: ${formatMoney(payload.cancellation_fee_cents)}`;
    return "Trip fare ledger and charge components";
  }
  if (evidence.class === "app_event") return eventSummary(payload);
  if (evidence.class === "profile_history") return "Relevant account history for this trip";
  return "Source record attached to this case";
}

function eventSummary(payload: Record<string, unknown>): string {
  const event = payload.event_type ?? payload.event;
  if (event) return humanize(String(event));
  const entries = Object.entries(payload).filter(([key, value]) => !key.startsWith("_") && value !== null && value !== undefined);
  const timing = entries.find(([key]) => /arrival|cancel|pickup|complete|wait/i.test(key));
  return timing ? `${labelForField(timing[0])}: ${String(timing[1])}` : "Recorded trip timeline event";
}

function pointsForEvidence(evidence: Evidence): Point[] {
  const payload = evidence.payload;
  const route = asRecord(payload.route);
  const routeMap = asRecord(payload.route_map);
  const candidates = [
    ...arrayAt(routeMap, "observed_samples"), ...arrayAt(routeMap, "planned_waypoints"),
    routeMap.pickup, routeMap.dropoff,
    ...arrayAt(payload, "observed_samples"), ...arrayAt(payload, "samples"),
    ...arrayAt(route, "waypoints"), ...arrayAt(payload, "waypoints"),
    payload,
  ];
  const points = candidates.map((item) => {
    const point = asRecord(item);
    return { lat: Number(point.lat ?? point.latitude), lon: Number(point.lon ?? point.lng ?? point.longitude) };
  }).filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lon) && Math.abs(point.lat) <= 90 && Math.abs(point.lon) <= 180);
  return points.filter((point, index) => index === 0 || point.lat !== points[index - 1].lat || point.lon !== points[index - 1].lon);
}

function labelForField(path: string): string {
  const field = path.split(".").at(-1) ?? path;
  const labels: Record<string, string> = {
    actual_distance_km: "Recorded distance", planned_distance_km: "Planned distance", deviation_pct: "Distance difference",
    min_distance_to_pickup_m: "Closest point to pickup", driver_waited_seconds: "Driver waiting time",
    contact_attempt_recorded: "Driver contact attempt", quoted_fare_cents: "Quoted fare", charged_fare_cents: "Charged fare",
    cancellation_fee_cents: "Cancellation fee", waiting_fare_cents: "Waiting fee", surge_multiplier: "Surge multiplier",
    latitude: "GPS location", longitude: "GPS location", accuracy_m: "GPS accuracy", status: "GPS event",
  };
  return labels[field] ?? humanize(field);
}

function formatObservedValue(fieldPath: string, value: unknown): string {
  if (value === undefined || value === null) return "Not available";
  const field = fieldPath.split(".").at(-1) ?? fieldPath;
  if (/(_fare_cents|_fee_cents|_cents)$/.test(field)) return formatMoney(value);
  if (field === "actual_distance_km" || field === "planned_distance_km") return formatDistance(value);
  if (field === "deviation_pct") return `${formatNumber(value)}%`;
  if (field === "min_distance_to_pickup_m" || field === "accuracy_m") return `${formatNumber(value)} m`;
  if (field === "driver_waited_seconds") return `${Math.round(Number(value) / 60)} min`;
  if (field === "surge_multiplier") return `${formatNumber(value)}×`;
  if (typeof value === "boolean") return value ? "Recorded" : "Not recorded";
  if (field === "latitude" || field === "longitude") return "Location shown on map";
  if (typeof value === "number") return formatNumber(value);
  return String(value);
}

function formatMoney(value: unknown): string {
  return new Intl.NumberFormat("en-SG", { style: "currency", currency: "SGD" }).format(Number(value) / 100);
}
function formatDistance(value: unknown): string { return `${formatNumber(value)} km`; }
function formatNumber(value: unknown): string {
  const number = Number(value);
  return Number.isFinite(number) ? new Intl.NumberFormat("en-SG", { maximumFractionDigits: 1 }).format(number) : String(value);
}
function evidenceLabel(value?: Evidence["class"]): string { return value ? labelForEvidenceClass(value) : "Case evidence"; }
function iconForEvidence(kind?: string, field?: string): string {
  if (kind === "gps_telemetry" || /latitude|longitude|location/i.test(field ?? "")) return "⌖";
  if (kind === "chat_log") return "“";
  if (kind === "fare") return "S$";
  if (kind === "app_event") return "◷";
  if (kind === "profile_history") return "◎";
  return "▤";
}
function humanize(value: string): string { return value.replaceAll("_", " ").replaceAll(".", " · ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function asRecord(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function arrayAt(value: Record<string, unknown>, key: string): unknown[] { const items = value[key]; return Array.isArray(items) ? items : []; }
function readField(payload: Record<string, unknown>, path: string): unknown {
  let current: unknown = payload;
  for (const part of path.replace(/^payload\./, "").split(".")) current = asRecord(current)[part];
  return current;
}
function clamp(value: number, min: number, max: number): number { return Math.min(max, Math.max(min, value)); }
function clampPanelPosition(position: PanelPosition): PanelPosition {
  const panelWidth = Math.min(720, window.innerWidth - 32);
  const panelHeight = Math.min(window.innerHeight - 32, 820);
  return {
    x: clamp(position.x, 16, Math.max(16, window.innerWidth - panelWidth - 16)),
    y: clamp(position.y, 16, Math.max(16, window.innerHeight - panelHeight - 16)),
  };
}

export function VerificationBadge({ status, uncertaintyPct, size = "md" }: { status: string; uncertaintyPct?: number | null; size?: "sm" | "md" }) {
  const className = status === "verified" ? "verified" : status === "unverified" ? "unverified" : status === "disputed" ? "disputed" : "unknown";
  return <span className={`verification-badge ${className} ${size}`} data-testid="verification-badge">
    <span>{labelForVerificationStatus(status)}</span>
    {uncertaintyPct != null && <span title="Uncertainty percentage">±{uncertaintyPct}%</span>}
  </span>;
}
