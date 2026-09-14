export function TopBar() {
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center gap-2.5 px-5 py-3 sm:px-8">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-sm font-bold text-[rgb(var(--on-accent))]">
          F
        </span>
        <span className="text-sm font-semibold text-ink">Financial Overview</span>
        <span className="ml-auto text-xs text-subtle">Companies House · Claude</span>
      </div>
    </header>
  );
}
