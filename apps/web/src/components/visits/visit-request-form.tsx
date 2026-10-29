"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/components/auth/problem-message";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import { analyticsId } from "@/lib/analytics-beacon";
import { ApiError } from "@/lib/api/errors";
import { VISITS_PATH } from "@/lib/auth/routes";
import { z } from "@/lib/forms/zod";
import { requestVisit } from "@/lib/visits/client";
import { visitStart } from "@/lib/visits/times";

export interface VisitRequestText {
  /** One label per choice: "Time 1", "Time 2 (if you like)", … */
  slots: readonly string[];
  day: string;
  time: string;
  chooseDay: string;
  chooseTime: string;
  needOne: string;
  needBoth: string;
  submit: string;
  submitting: string;
  errors: Record<string, string>;
}

interface Option {
  value: string;
  label: string;
}

// The three choices' fields, named outright so the form's paths stay typed.
const FIELDS = [
  { day: "slots.0.day", time: "slots.0.time" },
  { day: "slots.1.day", time: "slots.1.time" },
  { day: "slots.2.day", time: "slots.2.time" },
] as const;

const selectClasses =
  "h-11 w-full rounded-md border bg-background px-3 text-base shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-invalid:border-destructive md:text-sm dark:bg-input/30";

/**
 * Up to three times a student could come (step 3.7): a day and a time each, the first needed.
 * Nothing is chosen for them. Ops call to book one; the API checks the times again.
 */
export function VisitRequestForm({
  slug,
  days,
  times,
  text,
}: {
  slug: string;
  days: readonly Option[];
  times: readonly Option[];
  text: VisitRequestText;
}) {
  const router = useRouter();
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const slot = z.object({ day: z.string(), time: z.string() });
  const schema = z
    .object({ slots: z.array(slot).length(FIELDS.length) })
    .superRefine(({ slots }, context) => {
      slots.forEach(({ day, time }, index) => {
        if (index === 0 && (day === "" || time === "")) {
          context.addIssue({ code: "custom", path: ["slots", 0, "day"], message: text.needOne });
        } else if ((day === "") !== (time === "")) {
          context.addIssue({
            code: "custom",
            path: ["slots", index, "day"],
            message: text.needBoth,
          });
        }
      });
    });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { slots: FIELDS.map(() => ({ day: "", time: "" })) },
  });
  const { errors, isSubmitting } = form.formState;

  async function submit(values: Values) {
    setFailure(null);
    const starts = values.slots
      .filter(({ day, time }) => day !== "" && time !== "")
      .map(({ day, time }) => visitStart(day, time));
    try {
      await requestVisit(slug, starts, analyticsId());
      track("visit_requested", { slug, times: starts.length });
      router.push(VISITS_PATH);
      router.refresh();
    } catch (error) {
      // The API's own words for times it can't take ("less than three hours away").
      if (error instanceof ApiError && error.code === "VISIT_INVALID") {
        setFailure(error.problem?.detail ?? text.errors.generic ?? "");
        return;
      }
      setFailure(problemMessage(error, text.errors));
    }
  }

  return (
    <form
      noValidate
      onSubmit={(event) => {
        void form.handleSubmit(submit)(event);
      }}
      className="space-y-6"
    >
      {FIELDS.map((field, index) => {
        const label = text.slots[index] ?? "";
        const problem = errors.slots?.[index]?.day?.message;
        const problemId = `${id}-slot-${String(index)}-problem`;
        return (
          <fieldset
            key={label}
            className="space-y-2"
            aria-describedby={problem ? problemId : undefined}
          >
            <legend className="font-medium">{label}</legend>
            <div className="grid grid-cols-2 gap-3">
              <label className="space-y-1.5 text-sm">
                <span>{text.day}</span>
                <select
                  {...form.register(field.day)}
                  aria-invalid={problem ? true : undefined}
                  className={selectClasses}
                >
                  <option value="">{text.chooseDay}</option>
                  {days.map((day) => (
                    <option key={day.value} value={day.value}>
                      {day.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-1.5 text-sm">
                <span>{text.time}</span>
                <select
                  {...form.register(field.time)}
                  aria-invalid={problem ? true : undefined}
                  className={selectClasses}
                >
                  <option value="">{text.chooseTime}</option>
                  {times.map((time) => (
                    <option key={time.value} value={time.value}>
                      {time.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {problem ? (
              <p id={problemId} className="text-sm text-destructive">
                {problem}
              </p>
            ) : null}
          </fieldset>
        );
      })}
      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
      <Button type="submit" size="lg" disabled={isSubmitting}>
        {isSubmitting ? text.submitting : text.submit}
      </Button>
    </form>
  );
}
