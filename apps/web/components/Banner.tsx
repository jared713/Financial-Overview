export function Banner({
  tone,
  children,
}: {
  tone: "red" | "amber";
  children: React.ReactNode;
}) {
  const tones = {
    red: "border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200",
    amber:
      "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200",
  };
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm shadow-card ${tones[tone]}`}>
      {children}
    </div>
  );
}
