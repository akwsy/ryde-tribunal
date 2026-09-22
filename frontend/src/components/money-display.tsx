import { formatMoney, formatMoneyA11y } from "@/lib/api/money";
import type { Money } from "@/lib/api/types";

/**
 * Displays a monetary amount from integer cents + currency code.
 *
 * Rules (docs/02-api-contract.md §1 Display rules — Money):
 * - formatMoney converts once, in one helper. Never divides in a template.
 * - Never parses a float, never does arithmetic on a display string.
 *
 * 325 SGD → S$3.25, 0 SGD → S$0.00.
 */
export function MoneyDisplay({
  money,
  size = "md",
}: {
  money: Money | null | undefined;
  size?: "sm" | "md" | "lg";
}) {
  if (!money) {
    return <span className="text-gray-500 italic">No amount specified</span>;
  }

  const display = formatMoney(money);
  const a11y = formatMoneyA11y(money);

  const sizeClasses =
    size === "sm" ? "text-sm" : size === "lg" ? "text-2xl font-bold" : "text-lg font-semibold";

  return (
    <span
      className={sizeClasses}
      aria-label={a11y}
      data-testid="money-display"
      data-amount-cents={money.amount_cents}
      data-currency={money.currency}
    >
      {display}
    </span>
  );
}
