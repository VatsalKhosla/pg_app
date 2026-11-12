/**
 * How many things are in each status: a label, a bar to scale and the count. The text carries the
 * number; the bar only shows its share.
 */
export function StatusBars({
  id,
  title,
  rows,
}: {
  id: string;
  title: string;
  rows: readonly { key: string; label: string; count: number }[];
}) {
  const most = Math.max(1, ...rows.map((row) => row.count));
  return (
    <section
      aria-labelledby={`${id}-title`}
      className="rounded-[1.75rem] border border-border/70 bg-card p-5 shadow-md sm:p-6"
    >
      <h2 id={`${id}-title`} className="font-sans text-base font-semibold text-foreground">
        {title}
      </h2>
      <dl className="mt-4 grid gap-2.5">
        {rows.map((row) => (
          <div
            key={row.key}
            className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3"
          >
            <dt className="truncate text-sm text-muted-foreground">{row.label}</dt>
            <span aria-hidden="true" className="h-2.5 overflow-hidden rounded-full bg-muted">
              <span
                className="block h-full rounded-full bg-chart-series"
                style={{ width: `${String(Math.round((row.count / most) * 100))}%` }}
              />
            </span>
            <dd className="text-sm font-semibold text-foreground tabular-nums">{row.count}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
