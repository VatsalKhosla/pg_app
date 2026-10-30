import type { Schemas } from "@pg-platform/api-client";
import type { Metadata } from "next";
import { getFormatter, getTranslations } from "next-intl/server";

import { type PolicyField, PolicyForm, type PolicyName } from "@/components/admin/policy-form";
import { bpsToPercentInput } from "@/lib/forms/units";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { ADMIN_POLICIES_PATH } from "@/lib/auth/routes";
import { requireAdmin } from "@/lib/auth/session";
import { formatINR, paiseToRupeesInput } from "@/lib/money";

type Fee = Schemas["FeePolicyVersionInfo"];
type Booking = Schemas["BookingPolicyVersionInfo"];
type Caps = Schemas["PricingCapsVersionInfo"];

const BASIS_POINTS = 10_000;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Admin.policies");
  return { title: t("metaTitle") };
}

/**
 * The policies money follows (step 4.1, ADR 0036): each one in force, a form for its next
 * version, and its recent versions. Admins only; the API checks again and audits every change.
 */
export default async function AdminPoliciesPage() {
  await requireAdmin(ADMIN_POLICIES_PATH);
  const api = await getServerApi();
  const [current, history, t, format] = await Promise.all([
    unwrap(api.GET("/v1/admin/policies")),
    unwrap(api.GET("/v1/admin/policies/history")),
    getTranslations("Admin.policies"),
    getFormatter(),
  ]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "medium", timeStyle: "short" });
  const percent = (bps: number) =>
    format.number(bps / BASIS_POINTS, { style: "percent", maximumFractionDigits: 2 });
  const by = (version: Fee | Booking | Caps) =>
    version.changedBy === null ? t("seeded") : (version.changedBy.name ?? t("someone"));

  const summaries = {
    fee: (version: Fee) =>
      t("fee.summary", {
        rate: percent(version.rateBps),
        gst: percent(version.gstRateBps),
        mode:
          version.gstMode === "exclusive" ? t("fee.summaryExclusive") : t("fee.summaryInclusive"),
      }),
    booking: (version: Booking) =>
      t("booking.summary", {
        token: formatINR(version.tokenPaise),
        days: version.freeCancelDays,
      }),
    caps: (version: Caps) =>
      t("caps.summary", {
        premium: percent(version.maxPremiumBps),
        discount: percent(version.maxDiscountBps),
        step: formatINR(version.roundingStepPaise),
      }),
  };

  const fee = current.fee;
  const booking = current.booking;
  const caps = current.caps;
  const sections: {
    policy: PolicyName;
    title: string;
    inForce: Fee | Booking | Caps;
    summary: string;
    fields: PolicyField[];
    initial: Record<string, string>;
    history: { from: string; to: string | null; summary: string; by: string; note: string }[];
  }[] = [
    {
      policy: "fee",
      title: t("fee.title"),
      inForce: fee,
      summary: summaries.fee(fee),
      fields: [
        { name: "rateBps", label: t("fee.rate"), hint: t("fee.rateHint"), kind: "percent" },
        { name: "gstRateBps", label: t("fee.gstRate"), kind: "percent" },
        {
          name: "gstMode",
          label: t("fee.gstMode"),
          kind: "choice",
          choices: [
            { value: "exclusive", label: t("fee.exclusive") },
            { value: "inclusive", label: t("fee.inclusive") },
          ],
        },
      ],
      initial: {
        rateBps: bpsToPercentInput(fee.rateBps),
        gstRateBps: bpsToPercentInput(fee.gstRateBps),
        gstMode: fee.gstMode,
      },
      history: history.fee.map((version) => ({
        from: version.effectiveFrom,
        to: version.effectiveTo,
        summary: summaries.fee(version),
        by: by(version),
        note: version.note,
      })),
    },
    {
      policy: "booking",
      title: t("booking.title"),
      inForce: booking,
      summary: summaries.booking(booking),
      fields: [
        {
          name: "tokenPaise",
          label: t("booking.token"),
          hint: t("booking.tokenHint"),
          kind: "rupees",
        },
        { name: "holdMinutes", label: t("booking.holdMinutes"), kind: "whole" },
        { name: "freeCancelDays", label: t("booking.freeCancelDays"), kind: "whole" },
        { name: "checkWindowHours", label: t("booking.checkWindowHours"), kind: "whole" },
        { name: "confirmDeadlineHours", label: t("booking.confirmDeadlineHours"), kind: "whole" },
        { name: "noShowDays", label: t("booking.noShowDays"), kind: "whole" },
        {
          name: "lateCancelPolicy",
          label: t("booking.lateCancelPolicy"),
          kind: "choice",
          choices: (["refund_full", "forfeit_to_owner", "split"] as const).map((value) => ({
            value,
            label: t(`booking.${value}`),
          })),
        },
        { name: "maxActiveHoldsPerUser", label: t("booking.maxActiveHolds"), kind: "whole" },
        { name: "maxAdvanceDays", label: t("booking.maxAdvanceDays"), kind: "whole" },
      ],
      initial: {
        tokenPaise: paiseToRupeesInput(booking.tokenPaise),
        holdMinutes: String(booking.holdMinutes),
        freeCancelDays: String(booking.freeCancelDays),
        checkWindowHours: String(booking.checkWindowHours),
        confirmDeadlineHours: String(booking.confirmDeadlineHours),
        noShowDays: String(booking.noShowDays),
        lateCancelPolicy: booking.lateCancelPolicy,
        maxActiveHoldsPerUser: String(booking.maxActiveHoldsPerUser),
        maxAdvanceDays: String(booking.maxAdvanceDays),
      },
      history: history.booking.map((version) => ({
        from: version.effectiveFrom,
        to: version.effectiveTo,
        summary: summaries.booking(version),
        by: by(version),
        note: version.note,
      })),
    },
    {
      policy: "caps",
      title: t("caps.title"),
      inForce: caps,
      summary: summaries.caps(caps),
      fields: [
        { name: "maxPremiumBps", label: t("caps.premium"), kind: "percent" },
        { name: "maxDiscountBps", label: t("caps.discount"), kind: "percent" },
        { name: "roundingStepPaise", label: t("caps.roundingStep"), kind: "rupees" },
      ],
      initial: {
        maxPremiumBps: bpsToPercentInput(caps.maxPremiumBps),
        maxDiscountBps: bpsToPercentInput(caps.maxDiscountBps),
        roundingStepPaise: paiseToRupeesInput(caps.roundingStepPaise),
      },
      history: history.caps.map((version) => ({
        from: version.effectiveFrom,
        to: version.effectiveTo,
        summary: summaries.caps(version),
        by: by(version),
        note: version.note,
      })),
    },
  ];

  return (
    <div className="space-y-10">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      {sections.map((section) => (
        <section
          key={section.policy}
          aria-labelledby={`${section.policy}-title`}
          className="space-y-5 rounded-lg border p-5"
        >
          <div className="space-y-1">
            <h2 id={`${section.policy}-title`} className="text-xl font-semibold">
              {section.title}
            </h2>
            <p className="font-medium">{section.summary}</p>
            <p className="text-sm text-muted-foreground">
              {t("inForce", {
                since: when(section.inForce.effectiveFrom),
                by: by(section.inForce),
              })}
            </p>
          </div>
          <PolicyForm policy={section.policy} fields={section.fields} initial={section.initial} />
          <details className="space-y-2">
            <summary className="cursor-pointer text-sm font-medium">{t("historyTitle")}</summary>
            <ol className="space-y-2 pt-2">
              {section.history.map((version) => (
                <li key={version.from} className="text-sm">
                  <p>
                    {t("historyFrom", { from: when(version.from) })}{" "}
                    {version.to === null
                      ? t("historyNow")
                      : t("historyTo", { to: when(version.to) })}
                    {" · "}
                    {version.summary}
                  </p>
                  <p className="text-muted-foreground">
                    {version.by}
                    {version.note === "" ? null : ` · ${version.note}`}
                  </p>
                </li>
              ))}
            </ol>
          </details>
        </section>
      ))}
    </div>
  );
}
