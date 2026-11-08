"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import type { ReactNode, SubmitEvent } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface Choice {
  value: string;
  label: string;
}

export interface HeroSearchText {
  label: string;
  near: string;
  anywhere: string;
  moveIn: string;
  anyMonth: string;
  budget: string;
  anyBudget: string;
  submit: string;
}

const selectClasses =
  "w-full cursor-pointer appearance-none truncate border-0 bg-transparent p-0 pr-5 text-base font-medium text-foreground outline-none sm:text-sm";

function Field({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label
      className={cn(
        "flex min-h-14 min-w-0 cursor-pointer flex-col justify-center rounded-3xl px-5 py-2 transition-colors duration-(--duration-fast) focus-within:ring-2 focus-within:ring-ring hover:bg-foreground/5 motion-reduce:transition-none",
        className,
      )}
    >
      <span className="text-xs font-semibold text-foreground">{label}</span>
      {children}
    </label>
  );
}

/**
 * The search over the hero's bottom edge. Without its script it is still a plain form that goes to
 * /search; with it, the choices left at "any" stay out of the address, and the move is a soft one.
 */
export function HeroSearch({
  text,
  campuses,
  months,
  budgets,
}: {
  text: HeroSearchText;
  campuses: readonly Choice[];
  months: readonly Choice[];
  budgets: readonly Choice[];
}) {
  const router = useRouter();

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = new URLSearchParams();
    for (const [key, value] of new FormData(event.currentTarget)) {
      if (typeof value === "string" && value !== "") query.set(key, value);
    }
    const search = query.toString();
    router.push(search === "" ? "/search" : `/search?${search}`);
  }

  return (
    <form
      method="get"
      action="/search"
      onSubmit={submit}
      aria-label={text.label}
      className="glass grid grid-cols-2 gap-1 rounded-[2rem] p-2 shadow-xl sm:grid-cols-[1.5fr_1fr_1fr_auto] sm:items-center sm:rounded-full"
    >
      <Field label={text.near} className="col-span-2 sm:col-span-1">
        <select name="campus" defaultValue="" className={selectClasses}>
          <option value="">{text.anywhere}</option>
          {campuses.map((campus) => (
            <option key={campus.value} value={campus.value}>
              {campus.label}
            </option>
          ))}
        </select>
      </Field>
      <Field label={text.moveIn}>
        <select name="move_in_month" defaultValue="" className={selectClasses}>
          <option value="">{text.anyMonth}</option>
          {months.map((month) => (
            <option key={month.value} value={month.value}>
              {month.label}
            </option>
          ))}
        </select>
      </Field>
      <Field label={text.budget}>
        <select name="budget_max_paise" defaultValue="" className={selectClasses}>
          <option value="">{text.anyBudget}</option>
          {budgets.map((budget) => (
            <option key={budget.value} value={budget.value}>
              {budget.label}
            </option>
          ))}
        </select>
      </Field>
      <Button
        type="submit"
        variant="sun"
        size="lg"
        shape="pill"
        className="col-span-2 h-14 sm:col-span-1 pointer-fine:h-14"
      >
        <Search aria-hidden="true" />
        {text.submit}
      </Button>
    </form>
  );
}
