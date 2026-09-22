/**
 * Visible badge rendered whenever synthetic_reasoning is true (integrity rule I-6).
 *
 * The flag means a scripted fallback produced the text rather than a model.
 * Presenting it as advocate or Judge reasoning without the badge misrepresents
 * the system. This is an acceptance criterion.
 *
 * When synthetic_reasoning is false, this component renders nothing.
 */
export function SyntheticBadge({
  show,
  size = "md",
}: {
  show: boolean;
  size?: "sm" | "md";
}) {
  if (!show) return null;

  const sizeClasses =
    size === "sm"
      ? "text-xs px-2 py-0.5 gap-1"
      : "text-sm px-2.5 py-1 gap-1.5";

  return (
    <span
      role="status"
      aria-label="Synthetic reasoning: this output was produced by a scripted fallback, not a model"
      className={`inline-flex items-center ${sizeClasses} rounded-full bg-tribunal-synthetic/10 border border-tribunal-synthetic/30 text-tribunal-synthetic font-medium`}
      data-testid="synthetic-reasoning-badge"
    >
      <svg
        className={size === "sm" ? "w-3 h-3" : "w-4 h-4"}
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
          clipRule="evenodd"
        />
      </svg>
      Synthetic Reasoning
    </span>
  );
}
