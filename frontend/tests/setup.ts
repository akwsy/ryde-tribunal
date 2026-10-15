import "@testing-library/jest-dom";
import { vi } from "vitest";

// Leaflet needs a real layout engine. Browser acceptance checks exercise the real map;
// component tests keep the lazy map as a placeholder.
vi.mock("next/dynamic", () => ({ default: () => () => null }));

if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Polyfill for matchMedia (not available in jsdom)
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}
