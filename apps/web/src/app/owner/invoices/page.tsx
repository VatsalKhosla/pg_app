import type { Metadata } from "next";
import { getFormatter, getTranslations } from "next-intl/server";

import { NotSetUp } from "@/components/owner/not-set-up";
import { PayInvoice } from "@/components/owner/pay-invoice";
import { publicEnv } from "@/config/env";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OWNER_INVOICES_PATH } from "@/lib/auth/routes";
import { requireOwner } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";
import { getOwnProfile } from "@/lib/owner/server";

const PAGE = 50;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Owner.invoices");
  return { title: t("metaTitle") };
}

/** A rate in basis points as people write it: 30%, 12.5%. */
function percent(bps: number): string {
  return `${String(bps / 100)}%`;
}

/**
 * The owner's invoices (step 6.5, ADR 0061): for each tenant placed, the fee and its GST, what the
 * student's token paid, and the balance, with its payment link and the PDF. Amounts are the API's;
 * nothing is worked out here.
 */
export default async function OwnerInvoicesPage() {
  await requireOwner(OWNER_INVOICES_PATH);
  const owner = await getOwnProfile();
  if (owner === null) return <NotSetUp />;
  const api = await getServerApi();
  const page = await unwrap(api.GET("/v1/owner/invoices", { params: { query: { limit: PAGE } } }));
  const [t, format] = await Promise.all([getTranslations("Owner.invoices"), getFormatter()]);
  const day = (moment: string) => format.dateTime(new Date(moment), { dateStyle: "medium" });

  return (
    <>
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      {page.items.length === 0 ? (
        <p>{t("none")}</p>
      ) : (
        <ul className="space-y-6">
          {page.items.map((invoice) => {
            const terms = {
              rate: percent(invoice.feeRateBps),
              rent: formatINR(invoice.baseRentPaise),
            };
            const rows = [
              { term: t("taxable"), value: formatINR(invoice.feePaise) },
              {
                term: t("gst", { rate: percent(invoice.gstRateBps) }),
                value: formatINR(invoice.gstPaise),
              },
              { term: t("total"), value: formatINR(invoice.totalPaise) },
              { term: t("token"), value: `−${formatINR(invoice.tokenAppliedPaise)}` },
              { term: t("balance"), value: formatINR(invoice.balanceDuePaise) },
            ];
            return (
              <li key={invoice.id}>
                <section
                  aria-labelledby={`invoice-${invoice.id}`}
                  className="space-y-3 rounded-lg border p-4"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h2 id={`invoice-${invoice.id}`} className="text-lg font-semibold">
                      {t("number", { number: invoice.number })}
                    </h2>
                    <span className="text-sm font-medium">{t(`status.${invoice.status}`)}</span>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {t("issued", { date: day(invoice.issuedAt) })} ·{" "}
                    {t("booking", { code: invoice.booking, place: invoice.place })}
                  </p>
                  <p className="text-sm">
                    {invoice.gstIncluded ? t("feeIncluded", terms) : t("fee", terms)}
                  </p>
                  <dl aria-label={t("amounts")} className="divide-y rounded-md border text-sm">
                    {rows.map((row) => (
                      <div key={row.term} className="flex justify-between gap-4 p-2">
                        <dt>{row.term}</dt>
                        <dd className="tabular-nums">{row.value}</dd>
                      </div>
                    ))}
                  </dl>
                  {invoice.tokenOverPaise > 0 ? (
                    <p className="text-sm">
                      {t("over", { amount: formatINR(invoice.tokenOverPaise) })}
                    </p>
                  ) : null}
                  {invoice.paidAt === null ? null : (
                    <p className="text-sm">{t("paidOn", { date: day(invoice.paidAt) })}</p>
                  )}
                  <div className="flex flex-wrap items-start gap-4">
                    {invoice.status === "issued" ? (
                      <PayInvoice
                        id={invoice.id}
                        pay={invoice.pay}
                        text={{
                          pay: t("pay", { amount: formatINR(invoice.balanceDuePaise) }),
                          payNote: t("payNote"),
                          noLink: t("noLink"),
                          test: {
                            title: t("test.title"),
                            body: t("test.body"),
                            pay: t("test.pay", { amount: formatINR(invoice.balanceDuePaise) }),
                            cancel: t("test.cancel"),
                            paid: t("test.paid"),
                            failed: t("test.failed"),
                          },
                        }}
                      />
                    ) : null}
                    {invoice.hasFile ? (
                      <a
                        href={`${publicEnv.browserApiOrigin}/v1/owner/invoices/${invoice.id}/file`}
                        className="inline-flex min-h-9 items-center text-sm font-medium text-primary underline underline-offset-4"
                      >
                        {t("download")}
                      </a>
                    ) : (
                      <p className="text-sm text-muted-foreground">{t("preparing")}</p>
                    )}
                  </div>
                </section>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
