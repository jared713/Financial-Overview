export function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return null;
  const tone =
    status === "active"
      ? "badge-green"
      : status === "dissolved" || status.includes("liquidation")
        ? "badge-amber"
        : "badge-neutral";
  return <span className={tone}>{status.replace(/-/g, " ")}</span>;
}
