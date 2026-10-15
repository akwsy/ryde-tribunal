"use client";

import { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { Evidence } from "@/lib/api/types";
import type { LatLngBoundsExpression, LatLngExpression } from "leaflet";

type Point = { lat: number; lon: number; label?: string; recorded_at?: string; accuracy_m?: number };

export default function EvidenceMap({ evidence, points: _points }: { evidence: Evidence; points: Point[] }) {
  const [tileError, setTileError] = useState(false);
  const routeMap = asRecord(evidence.payload.route_map);
  const pickup = asPoint(routeMap.pickup);
  const dropoff = asPoint(routeMap.dropoff);
  const planned = pointList(routeMap.planned_waypoints);
  const observed = pointList(routeMap.observed_samples);
  const legacyRoute = asRecord(evidence.payload.route);
  const legacyWaypoints = pointList(legacyRoute.waypoints ?? evidence.payload.waypoints);
  const samples = pointList(evidence.payload.samples ?? evidence.payload.observed_samples);
  const visibleObserved = observed.length ? observed : samples;
  const visiblePlanned = planned.length ? planned : legacyWaypoints;
  const allPoints = [pickup, dropoff, ...visiblePlanned, ...visibleObserved].filter((point): point is Point => Boolean(point));
  if (!allPoints.length) allPoints.push(..._points);
  const center = useMemo<LatLngExpression>(() => {
    if (!allPoints.length) return [1.3521, 103.8198];
    return [allPoints.reduce((sum, point) => sum + point.lat, 0) / allPoints.length,
      allPoints.reduce((sum, point) => sum + point.lon, 0) / allPoints.length];
  // The source record is loaded once for this mounted viewer.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evidence.evidence_id]);
  const bounds = allPoints.length > 1 ? allPoints.map((point) => [point.lat, point.lon] as [number, number]) as LatLngBoundsExpression : undefined;
  const tileUrl = process.env.NEXT_PUBLIC_MAP_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

  if (!allPoints.length) return null;

  return <section className="evidence-map-section" aria-label="Trip location map">
    <div className="evidence-map-heading"><h3>Trip locations</h3><span>{allPoints.length} recorded point{allPoints.length === 1 ? "" : "s"}</span></div>
    {tileError && <p className="evidence-map-fallback" role="status">Map tiles are unavailable. The recorded coordinates are still shown as a location diagram below.</p>}
    <div className={`evidence-map-frame${tileError ? " tiles-unavailable" : ""}`}>
      <MapContainer center={center} zoom={13} bounds={bounds} scrollWheelZoom={false} className="evidence-map" aria-label="Map of recorded trip locations">
        <TileLayer
          url={tileUrl}
          attribution={'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>'}
          eventHandlers={{ tileerror: () => setTileError(true) }}
        />
        <FitMap points={allPoints} />
        {visiblePlanned.length > 1 && <Polyline positions={visiblePlanned.map(({ lat, lon }) => [lat, lon])} pathOptions={{ color: "#64748b", weight: 4, dashArray: "7 7" }} />}
        {visibleObserved.length > 1 && <Polyline positions={visibleObserved.map(({ lat, lon }) => [lat, lon])} pathOptions={{ color: "#087f75", weight: 5 }} />}
        {allPoints.map((point, index) => <CircleMarker key={`${point.lat}-${point.lon}-${index}`} center={[point.lat, point.lon]} radius={index === 0 ? 8 : 6}
          pathOptions={{ color: point === pickup ? "#0f766e" : point === dropoff ? "#c2410c" : "#2563eb", fillOpacity: 0.9 }}>
          <Tooltip>{point.label || pointLabel(point, pickup, dropoff, index)}</Tooltip>
        </CircleMarker>)}
      </MapContainer>
      {tileError && <div className="evidence-map-schematic" aria-hidden="true">
        {allPoints.map((point, index) => <span key={`${point.lat}-${point.lon}-${index}`} style={{ left: `${project(point.lon, allPoints, "lon")}%`, top: `${project(point.lat, allPoints, "lat")}%` }} />)}
      </div>}
    </div>
    <ul className="evidence-map-legend"><li><span className="legend-pin pickup" />Pickup</li><li><span className="legend-pin dropoff" />Drop-off</li><li><span className="legend-line observed" />Recorded GPS</li><li><span className="legend-line planned" />Planned route</li></ul>
    <p className="evidence-map-note">Only the map area is requested from the tile provider. Case details and messages stay in this app.</p>
  </section>;
}

function FitMap({ points }: { points: Point[] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length > 1) map.fitBounds(points.map((point) => [point.lat, point.lon]), { padding: [24, 24], maxZoom: 15 });
    else if (points.length === 1) map.setView([points[0].lat, points[0].lon], 15);
  }, [map, points]);
  return null;
}
function pointList(value: unknown): Point[] { return Array.isArray(value) ? value.map(asPoint).filter((point): point is Point => Boolean(point)) : []; }
function asPoint(value: unknown): Point | null {
  const item = asRecord(value);
  const lat = Number(item.lat ?? item.latitude), lon = Number(item.lon ?? item.lng ?? item.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { lat, lon, label: typeof item.label === "string" ? item.label : undefined, recorded_at: typeof item.recorded_at === "string" ? item.recorded_at : undefined, accuracy_m: Number.isFinite(Number(item.accuracy_m)) ? Number(item.accuracy_m) : undefined };
}
function asRecord(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function pointLabel(point: Point, pickup: Point | null, dropoff: Point | null, index: number): string { return point === pickup ? "Pickup" : point === dropoff ? "Drop-off" : `GPS point ${index + 1}`; }
function project(value: number, points: Point[], axis: "lat" | "lon"): number {
  const values = points.map((point) => point[axis]);
  const min = Math.min(...values), max = Math.max(...values);
  return max === min ? 50 : 8 + ((value - min) / (max - min)) * 84;
}
