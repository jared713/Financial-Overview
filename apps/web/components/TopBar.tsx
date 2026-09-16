"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Companies" },
  { href: "/industry", label: "Industries" },
];

export function TopBar() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-4 border-b border-line bg-surface px-5 sm:px-6">
      <span className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-sm font-bold text-[rgb(var(--on-accent))]">
          F
        </span>
        <span className="hidden text-sm font-semibold text-ink sm:block">
          Financial Overview
        </span>
      </span>
      <nav className="flex items-center gap-1">
        {LINKS.map((link) => {
          const active =
            link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`rounded-md px-2.5 py-1 text-sm transition-colors ${
                active
                  ? "bg-accent-soft font-semibold text-accent"
                  : "text-muted hover:text-ink"
              }`}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
      <span className="ml-auto hidden text-xs text-subtle sm:block">
        Companies House · Claude
      </span>
    </header>
  );
}
