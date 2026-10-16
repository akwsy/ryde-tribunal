const GUEST_KEY = "ryde-demo-guest";
const PROFILE_KEY = "ryde-demo-profile";

export function setDemoProfile(mode: "guest" | "reviewer", profile?: string | null): void {
  if (typeof window === "undefined") return;
  if (mode === "guest") window.sessionStorage.setItem(GUEST_KEY, "yes");
  else window.sessionStorage.removeItem(GUEST_KEY);
  if (profile) window.sessionStorage.setItem(PROFILE_KEY, profile);
  else window.sessionStorage.removeItem(PROFILE_KEY);
}

export function clearDemoProfile(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(GUEST_KEY);
  window.sessionStorage.removeItem(PROFILE_KEY);
}

export function isGuestDemo(): boolean {
  return typeof window !== "undefined" && window.sessionStorage.getItem(GUEST_KEY) === "yes";
}

export function getDemoProfile(): string | null {
  return typeof window === "undefined" ? null : window.sessionStorage.getItem(PROFILE_KEY);
}
