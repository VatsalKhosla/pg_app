"use client";

import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { FormOutcome } from "@/components/ui/fields";
import { formatINR } from "@/lib/money";
import { bpsText, dayText, monthDayText, shareText } from "@/lib/pricing/editor";
import { removeRule } from "@/lib/pricing/editor-client";

import { useOpsProblem } from "../problems";
import { useRefresh } from "../use-refresh";
import { RuleForm } from "./rule-form";
import type { Rule } from "./rule-values";

type T = ReturnType<typeof useTranslations<"Ops.pricing">>;

/** A rule in a line: "+15% for move-ins from 1 Aug to 31 Aug, every year". */
function summaryOf(rule: Rule, t: T): string {
  const params = rule.params;
  switch (params.kind) {
    case "season":
      return t("rules.summary.season", {
        change: bpsText(params.bps),
        start: monthDayText(params.start),
        end: monthDayText(params.end),
      });
    case "early_bird":
      return t("rules.summary.early_bird", {
        change: bpsText(params.bps),
        days: params.minDaysBefore,
      });
    case "last_minute":
      return t("rules.summary.last_minute", {
        change: bpsText(params.bps),
        days: params.maxDaysBefore,
        taken: shareText(params.maxOccupancyBps),
      });
    case "occupancy":
      return params.tiers
        .map((tier) =>
          t("rules.summary.occupancyTier", {
            change: bpsText(tier.bps),
            taken: shareText(tier.minOccupancyBps),
          }),
        )
        .join("; ");
    case "length_of_stay":
      return params.tiers
        .map((tier) =>
          t("rules.summary.stayTier", { change: bpsText(tier.bps), months: tier.minMonths }),
        )
        .join("; ");
    case "override":
      return t("rules.summary.override", {
        rent: formatINR(params.rentPaise),
        start: dayText(params.start),
        end: dayText(params.end),
      });
  }
}

/**
 * A version's rules in the order they apply (step 4.6, ADR 0041). A draft's can be changed,
 * removed and added to; a version that has been in force never changes.
 */
export function RulesEditor({
  ruleSetId,
  rules,
  rooms,
  editable,
}: {
  ruleSetId: string;
  rules: readonly Rule[];
  rooms: readonly { id: string; label: string }[];
  editable: boolean;
}) {
  const t = useTranslations("Ops.pricing");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const [editing, setEditing] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function remove(rule: Rule) {
    setRemoving(rule.id);
    setFailure(null);
    try {
      await removeRule(rule.id);
      refresh();
    } catch (error) {
      setFailure(problem(error));
    } finally {
      setRemoving(null);
    }
  }

  return (
    <div className="space-y-4">
      {editable ? null : <p className="text-sm text-muted-foreground">{t("rules.readOnly")}</p>}
      {rules.length === 0 ? (
        <p>{t("rules.none")}</p>
      ) : (
        <ol className="space-y-3">
          {rules.map((rule) =>
            editing === rule.id ? (
              <li key={rule.id}>
                <RuleForm
                  ruleSetId={ruleSetId}
                  rule={rule}
                  rooms={rooms}
                  onDone={() => {
                    setEditing(null);
                  }}
                />
              </li>
            ) : (
              <li key={rule.id} className="space-y-2 rounded-lg border p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <h3 className="font-medium">{rule.label}</h3>
                  <p className="text-sm text-muted-foreground">
                    {[t(`rules.kinds.${rule.kind}`), rule.enabled ? null : t("rules.off")]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <p>{summaryOf(rule, t)}</p>
                <p className="text-sm text-muted-foreground">
                  {rule.roomCategories === null
                    ? t("rules.everyRoom")
                    : rule.roomCategories.map((category) => category.label).join(", ")}
                </p>
                {editable ? (
                  <div className="flex flex-wrap gap-2 pt-1">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      aria-label={t("rules.editRule", { label: rule.label })}
                      onClick={() => {
                        setEditing(rule.id);
                      }}
                    >
                      {t("rules.edit")}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={removing !== null}
                      aria-label={t("rules.removeRule", { label: rule.label })}
                      onClick={() => {
                        void remove(rule);
                      }}
                    >
                      {removing === rule.id ? t("rules.removing") : t("rules.remove")}
                    </Button>
                  </div>
                ) : null}
              </li>
            ),
          )}
        </ol>
      )}
      <FormOutcome failure={failure} />
      {editable ? (
        editing === "new" ? (
          <RuleForm
            ruleSetId={ruleSetId}
            rooms={rooms}
            onDone={() => {
              setEditing(null);
            }}
          />
        ) : (
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setEditing("new");
            }}
          >
            <Plus aria-hidden="true" />
            {t("rules.add")}
          </Button>
        )
      ) : null}
    </div>
  );
}
