export interface DateRange {
  from: string;
  to: string;
}

export type PeriodChoice = "day" | "week" | "month" | "custom";

/** Current calendar date in the dashboard's fixed business timezone. */
export function singaporeToday(now = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Singapore",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

/** Build day/week/month ranges; weeks start Sunday and all ranges include both endpoints. */
export function presetRange(choice: Exclude<PeriodChoice, "custom">, today = singaporeToday()): DateRange {
  const [year, month, day] = today.split("-").map(Number);
  const current = new Date(Date.UTC(year, month - 1, day));
  if (choice === "day") return { from: today, to: today };
  if (choice === "week") {
    const start = new Date(current);
    start.setUTCDate(start.getUTCDate() - start.getUTCDay());
    return { from: asDate(start), to: today };
  }
  const start = new Date(Date.UTC(year, month - 1, 1));
  return { from: asDate(start), to: today };
}

export function singaporeBoundary(date: string, end = false): string {
  return `${date}T${end ? "23:59:59.999" : "00:00:00"}+08:00`;
}

function asDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}
