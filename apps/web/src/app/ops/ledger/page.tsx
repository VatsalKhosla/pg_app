import type { Metadata } from "next";
import { getFormatter, getTranslations } from "next-intl/server";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_LEDGER_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";

// The API's limit.
const CODE_MAX_LENGTH = 32;
const PAGE = 50;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.ledger");
  return { title: t("metaTitle") };
}

/** A balance as an accountant reads it: debits plain, credits in brackets. */
function signed(paise: number): string {
  return paise < 0 ? `(${formatINR(-paise)})` : formatINR(paise);
}

/**
 * The books (step 6.4, ADR 0060): what every account holds, and what was posted, newest first, of
 * one booking if asked. Read only: postings come from the money events themselves.
 */
export default async function OpsLedgerPage({ searchParams }: PageProps<"/ops/ledger">) {
  await requireOps(OPS_LEDGER_PATH);
  const asked = (await searchParams).booking;
  const text = typeof asked === "string" ? asked.trim().slice(0, CODE_MAX_LENGTH) : "";
  const booking = text === "" ? undefined : text;
  const api = await getServerApi();
  const [balance, posted] = await Promise.all([
    unwrap(api.GET("/v1/ops/ledger/trial-balance", { params: { query: { booking } } })),
    unwrap(api.GET("/v1/ops/ledger/transactions", { params: { query: { booking, limit: PAGE } } })),
  ]);
  const [t, format] = await Promise.all([getTranslations("Ops.ledger"), getFormatter()]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="font-display text-title-1 text-foreground">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <form method="get" action={OPS_LEDGER_PATH} className="flex flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1 space-y-1">
          <label htmlFor="ledger-booking" className="text-sm font-medium">
            {t("search")}
          </label>
          <Input
            id="ledger-booking"
            name="booking"
            defaultValue={booking}
            maxLength={CODE_MAX_LENGTH}
            placeholder={t("searchHint")}
          />
        </div>
        <Button type="submit">{t("find")}</Button>
      </form>

      <section aria-labelledby="ledger-balance" className="space-y-3">
        <h2 id="ledger-balance" className="font-display text-title-3 text-foreground">
          {balance.booking === null
            ? t("balance.all")
            : t("balance.booking", { code: balance.booking })}
        </h2>
        <div className="overflow-x-auto rounded-2xl border border-border/80 bg-card shadow-xs">
          <table className="w-full min-w-96 text-sm">
            <thead>
              <tr className="border-b border-border/70 bg-surface/60 text-left">
                <th scope="col" className="p-3.5 font-medium text-muted-foreground">
                  {t("balance.account")}
                </th>
                <th scope="col" className="p-3.5 text-right font-medium text-muted-foreground">
                  {t("balance.debit")}
                </th>
                <th scope="col" className="p-3.5 text-right font-medium text-muted-foreground">
                  {t("balance.credit")}
                </th>
                <th scope="col" className="p-3.5 text-right font-medium text-muted-foreground">
                  {t("balance.balance")}
                </th>
              </tr>
            </thead>
            <tbody>
              {balance.lines.map((line) => (
                <tr key={line.account} className="border-b border-border/60 last:border-b-0">
                  <th scope="row" className="p-3.5 text-left font-normal text-foreground">
                    {line.name}
                  </th>
                  <td className="p-3.5 text-right tabular-nums">{formatINR(line.debitPaise)}</td>
                  <td className="p-3.5 text-right tabular-nums">{formatINR(line.creditPaise)}</td>
                  <td className="p-3.5 text-right font-medium text-foreground tabular-nums">
                    {signed(line.balancePaise)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-border/80 bg-surface/60 font-semibold text-foreground">
                <th scope="row" className="p-3.5 text-left">
                  {t("balance.total")}
                </th>
                <td className="p-3.5 text-right tabular-nums">
                  {formatINR(balance.totalDebitPaise)}
                </td>
                <td className="p-3.5 text-right tabular-nums">
                  {formatINR(balance.totalCreditPaise)}
                </td>
                <td className="p-3.5 text-right tabular-nums">
                  {signed(balance.totalDebitPaise - balance.totalCreditPaise)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>

      <section aria-labelledby="ledger-posted" className="space-y-3">
        <h2 id="ledger-posted" className="font-display text-title-3 text-foreground">
          {t("posted.title")}
        </h2>
        {posted.items.length === 0 ? (
          <p className="text-muted-foreground">{t("posted.none")}</p>
        ) : (
          <ul className="space-y-3">
            {posted.items.map((item) => (
              <li
                key={item.id}
                className="space-y-1.5 rounded-2xl border border-border/80 bg-card p-4 text-sm shadow-xs"
              >
                <p className="font-semibold text-foreground">{t(`posted.kind.${item.kind}`)}</p>
                <p className="text-muted-foreground tabular-nums">
                  {item.booking === null
                    ? when(item.postedAt)
                    : t("posted.line", { code: item.booking, when: when(item.postedAt) })}
                </p>
                <ul className="tabular-nums">
                  {item.entries.map((entry) => (
                    <li key={`${entry.account}-${entry.direction}`}>
                      {t(`posted.${entry.direction}`, {
                        account: entry.name,
                        amount: formatINR(entry.amountPaise),
                      })}
                    </li>
                  ))}
                </ul>
                {item.memo === "" ? null : <p>{t("posted.memo", { memo: item.memo })}</p>}
              </li>
            ))}
          </ul>
        )}
        {posted.nextCursor === null ? null : (
          <p className="text-sm text-muted-foreground">{t("posted.more", { count: PAGE })}</p>
        )}
      </section>
    </div>
  );
}
