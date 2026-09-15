export function TopBar() {
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-2.5 border-b border-line bg-surface px-5 sm:px-6">
      <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-sm font-bold text-[rgb(var(--on-accent))]">
        F
      </span>
      <span className="text-sm font-semibold text-ink">Financial Overview</span>
      <span className="ml-auto hidden text-xs text-subtle sm:block">
        Companies House · Claude
      </span>
    </header>
  );
}
