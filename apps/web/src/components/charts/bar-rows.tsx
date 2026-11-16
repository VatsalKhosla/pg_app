export interface BarRow {
  key: string;
  label: string;
  value: number;
  /** The value as people read it: "₹10,000", "14". */
  shown: string;
  /** A row to compare with, rather than the one that's the owner's own: drawn in grey. */
  muted?: boolean;
}

/**
 * Labelled horizontal bars on one scale (dataviz: magnitude, direct labels, so no legend): each
 * row's label and value written out, its bar as long as its share of ``max`` (the largest row
 * unless given, so several lists can share a scale). The bars are decoration; the words carry
 * every number.
 */
export function BarRows({
  label,
  rows,
  max,
}: {
  label: string;
  rows: readonly BarRow[];
  max?: number;
}) {
  const top = Math.max(max ?? 0, ...rows.map((row) => row.value));
  return (
    <ul aria-label={label} className="space-y-3">
      {rows.map((row) => {
        const share = top > 0 ? Math.min(Math.max(row.value / top, 0), 1) : 0;
        return (
          <li key={row.key} className="space-y-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
              <span className={row.muted === true ? "text-muted-foreground" : "font-medium"}>
                {row.label}
              </span>
              <span className="font-semibold text-foreground tabular-nums">{row.shown}</span>
            </div>
            <div aria-hidden="true" className="share-bar-track h-2.5 overflow-hidden rounded-full">
              {share > 0 ? (
                <div
                  className={`h-full rounded-full ${row.muted === true ? "share-bar-fill-muted" : "share-bar-fill"}`}
                  style={{ width: `${(share * 100).toFixed(1)}%` }}
                />
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
