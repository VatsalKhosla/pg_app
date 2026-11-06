import type { Schemas } from "@pg-platform/api-client";
import type { Metadata, Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { InvoiceLink } from "@/components/ops/invoice-link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { publicEnv } from "@/config/env";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_INVOICES_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";
import { cn } from "@/lib/utils";

type Status = Schemas["OpsInvoiceView"]["status"];

const STATUSES = ["issued", "paid"] as const satisfies readonly Status[];
// The API's limit.
const CODE_MAX_LENGTH = 32;
const PAGE = 50;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.invoices");
  return { title: t("metaTitle") };
}

/**
 * Owners' invoices (step 6.5, ADR 0061), newest first: to pay, paid, or one booking's. Ops download
 * the PDF, and ask for a new payment link when one was cancelled or refused.
 */
export default async function OpsInvoicesPage({ searchParams }: PageProps<"/ops/invoices">) {
  await requireOps(OPS_INVOICES_PATH);
  const asked = await searchParams;
  const status = STATUSES.find((each) => each === asked.status);
  const text =
    typeof asked.booking === "string" ? asked.booking.trim().slice(0, CODE_MAX_LENGTH) : "";
  const booking = text === "" ? undefined : text;
  const api = await getServerApi();
  const page = await unwrap(
    api.GET("/v1/ops/invoices", { params: { query: { status, booking, limit: PAGE } } }),
  );
  const [t, format] = await Promise.all([getTranslations("Ops.invoices"), getFormatter()]);
  const day = (moment: string) => format.dateTime(new Date(moment), { dateStyle: "medium" });
  const filters: { href: Route; label: string; current: boolean }[] = [
    { href: OPS_INVOICES_PATH, label: t("status.all"), current: status === undefined },
    ...STATUSES.map((each) => ({
      href: `${OPS_INVOICES_PATH}?status=${each}` as Route,
      label: t(`status.${each}`),
      current: each === status,
    })),
  ];

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-title-1 text-foreground">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <nav aria-label={t("statusFilter")} className="flex flex-wrap gap-2">
        {filters.map((filter) => (
          <Link
            key={filter.href}
            href={filter.href}
            aria-current={filter.current ? "page" : undefined}
            className={cn(
              "inline-flex min-h-9 items-center rounded-full border border-border/80 bg-card px-3.5 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-surface hover:text-foreground",
              filter.current &&
                "border-primary bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground",
            )}
          >
            {filter.label}
          </Link>
        ))}
      </nav>
      <form method="get" action={OPS_INVOICES_PATH} className="flex flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1 space-y-1">
          <label htmlFor="invoice-booking" className="text-sm font-medium">
            {t("search")}
          </label>
          <Input
            id="invoice-booking"
            name="booking"
            defaultValue={booking}
            maxLength={CODE_MAX_LENGTH}
            placeholder={t("searchHint")}
          />
        </div>
        <Button type="submit">{t("find")}</Button>
      </form>
      {page.items.length === 0 ? (
        <p className="text-muted-foreground">{t("none")}</p>
      ) : (
        <ul className="space-y-4">
          {page.items.map((invoice) => (
            <li
              key={invoice.id}
              className="space-y-2 rounded-2xl border border-border/80 bg-card p-5 shadow-xs"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-semibold text-foreground">
                  {t("line", { number: invoice.number, owner: invoice.owner })}
                </p>
                <span className="rounded-full bg-surface px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
                  {t(`status.${invoice.status}`)}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                {t("booking", {
                  code: invoice.booking,
                  place: invoice.place,
                  date: day(invoice.issuedAt),
                })}
              </p>
              <p className="text-sm tabular-nums">
                {t("amounts", {
                  total: formatINR(invoice.totalPaise),
                  token: formatINR(invoice.tokenAppliedPaise),
                  balance: formatINR(invoice.balanceDuePaise),
                })}
              </p>
              {invoice.tokenOverPaise > 0 ? (
                <p className="text-sm">
                  {t("over", { amount: formatINR(invoice.tokenOverPaise) })}
                </p>
              ) : null}
              {invoice.paidAt === null ? null : (
                <p className="text-sm">{t("paidOn", { date: day(invoice.paidAt) })}</p>
              )}
              <div className="flex flex-wrap items-center gap-4">
                {invoice.hasFile ? (
                  <a
                    href={`${publicEnv.browserApiOrigin}/v1/ops/invoices/${invoice.id}/file`}
                    className="inline-flex min-h-9 items-center text-sm font-medium text-primary underline underline-offset-4"
                  >
                    {t("download")}
                  </a>
                ) : (
                  <span className="text-sm text-muted-foreground">{t("preparing")}</span>
                )}
                {invoice.status === "issued" && invoice.pay !== null ? (
                  <span className="text-sm">{t("linkOut")}</span>
                ) : null}
                {invoice.status === "issued" && invoice.pay === null ? (
                  <InvoiceLink
                    id={invoice.id}
                    text={{
                      newLink: t("newLink"),
                      asked: t("asked"),
                      failed: t("linkFailed"),
                      exists: t("linkExists"),
                    }}
                  />
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
