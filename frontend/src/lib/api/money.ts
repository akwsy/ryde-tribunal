import type { Money } from "./types";

/**
 * Format an integer-cents amount + currency code into a display string.
 *
 * Contract: money is `amount_cents` (integer) + `currency` (3-letter code).
 * 325 SGD → "S$3.25". 0 SGD → "S$0.00".
 *
 * Display rules:
 * - Use Intl.NumberFormat('en-SG', { style: 'currency', currency }).
 * - Never parse a float. Never do arithmetic on a display string.
 * - Never divide amount_cents in a template — convert once, here, in this helper.
 */
export function formatMoney(money: Money): string {
  // amount_cents is already an integer from the API. We pass it to the formatter
  // by dividing by 100 here, inside this single function, so no other code ever
  // touches the division. This is the one place it happens.
  const majorUnits = money.amount_cents / 100;
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency: money.currency,
  }).format(majorUnits);
}

/**
 * Format for aria-label / tooltip — includes the raw cents for reviewer use.
 */
export function formatMoneyA11y(money: Money): string {
  return `${formatMoney(money)} (${money.amount_cents} ${money.currency} cents)`;
}
