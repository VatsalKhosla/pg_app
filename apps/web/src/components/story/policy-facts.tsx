import { getTranslations } from "next-intl/server";

import { getPolicies } from "@/lib/api/public";
import { formatINR } from "@/lib/money";

/** The promises, as figures from the live policy. Without the API there's nothing to state. */
export async function PolicyFacts() {
  let policies;
  try {
    policies = await getPolicies();
  } catch {
    return null;
  }
  const t = await getTranslations("Home.facts");
  const { tokenPaise, freeCancelDays, checkWindowHours } = policies.booking;
  const facts = [
    { value: formatINR(tokenPaise), label: t("token") },
    { value: t("days", { days: freeCancelDays }), label: t("cancel") },
    { value: t("hours", { hours: checkWindowHours }), label: t("check") },
    { value: formatINR(0), label: t("fee") },
  ];
  return (
    <section aria-labelledby="facts-title" className="mx-auto w-full max-w-page px-gutter">
      <h2 id="facts-title" className="sr-only">
        {t("title")}
      </h2>
      <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {facts.map((fact) => (
          <div
            key={fact.label}
            className="flex flex-col-reverse justify-end gap-1.5 rounded-[1.5rem] border border-border/70 bg-card/80 p-5 shadow-sm backdrop-blur-sm"
          >
            <dt className="text-sm leading-snug text-muted-foreground">{fact.label}</dt>
            <dd className="text-title-1 font-semibold text-primary tabular-nums">{fact.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
