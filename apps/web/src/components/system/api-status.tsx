import { getTranslations } from "next-intl/server";

import { type ApiHealth, getApiHealth } from "@/lib/api/health";
import { getServerApi } from "@/lib/api/server";
import { cn } from "@/lib/utils";

type Tone = ApiHealth | "checking";

const dotTone: Record<Tone, string> = {
  online: "bg-success",
  offline: "bg-warning-soft-foreground",
  checking: "bg-muted-foreground/50 motion-safe:animate-pulse",
};

// The text carries the state; the dot only repeats it in colour.
function StatusLine({ label, value, tone }: { label: string; value: string; tone: Tone }) {
  return (
    <p className="inline-flex items-center gap-2.5 rounded-full border bg-surface px-3.5 py-1.5 text-xs text-muted-foreground">
      <span aria-hidden className={cn("size-2 rounded-full", dotTone[tone])} />
      <span>
        {label}: <span className="font-semibold text-foreground">{value}</span>
      </span>
    </p>
  );
}

/** Whether the API is up, asked through the typed client. Stream it behind a Suspense boundary. */
export async function ApiStatus() {
  const [t, health] = await Promise.all([
    getTranslations("ApiStatus"),
    getServerApi().then(getApiHealth),
  ]);
  return <StatusLine label={t("label")} value={t(health)} tone={health} />;
}

/** Shown while ApiStatus waits for the API. */
export async function ApiStatusPending() {
  const t = await getTranslations("ApiStatus");
  return <StatusLine label={t("label")} value={t("checking")} tone="checking" />;
}
