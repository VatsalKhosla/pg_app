import type * as React from "react";
import type { UseFormRegisterReturn } from "react-hook-form";

import { cn } from "@/lib/utils";

/**
 * Form controls for the ops console: a label, the control, a hint and the field's error, wired
 * together for screen readers (aria-describedby, aria-invalid).
 */

export interface ControlProps {
  id: string;
  "aria-invalid": boolean;
  "aria-describedby": string | undefined;
}

function describedBy(id: string, hint: unknown, error: unknown): string | undefined {
  const ids = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean);
  return ids.length === 0 ? undefined : ids.join(" ");
}

function HintAndError({ id, hint, error }: { id: string; hint?: string; error?: string }) {
  return (
    <>
      {hint ? (
        <p id={`${id}-hint`} className="text-sm text-muted-foreground">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </>
  );
}

export function Field({
  id,
  label,
  hint,
  error,
  className,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string | undefined;
  className?: string;
  children: (control: ControlProps) => React.ReactNode;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {children({
        id,
        "aria-invalid": error !== undefined,
        "aria-describedby": describedBy(id, hint, error),
      })}
      <HintAndError id={id} {...(hint ? { hint } : {})} {...(error ? { error } : {})} />
    </div>
  );
}

const boxClasses =
  "w-full min-w-0 rounded-md border bg-transparent px-3 text-base shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none md:text-sm dark:bg-input/30";

export function Select({ className, ...props }: React.ComponentProps<"select">) {
  return <select className={cn(boxClasses, "h-11", className)} {...props} />;
}

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return <textarea className={cn(boxClasses, "min-h-24 py-2", className)} {...props} />;
}

/** A group of radio buttons, each a large target. */
export function Choices({
  id,
  legend,
  hint,
  error,
  options,
  registration,
  columns = 2,
}: {
  id: string;
  legend: string;
  hint?: string;
  error?: string | undefined;
  options: readonly { value: string; label: string }[];
  registration: UseFormRegisterReturn;
  columns?: 2 | 3;
}) {
  return (
    <fieldset className="space-y-2" aria-describedby={describedBy(id, hint, error)}>
      <legend className="text-sm font-medium">{legend}</legend>
      <div className={cn("grid gap-2", columns === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2")}>
        {options.map((option) => (
          <label
            key={option.value}
            className="flex min-h-11 items-center gap-3 rounded-md border px-3 text-sm has-[:checked]:border-primary has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/50"
          >
            <input
              type="radio"
              value={option.value}
              className="size-4 accent-primary"
              {...registration}
            />
            {option.label}
          </label>
        ))}
      </div>
      <HintAndError id={id} {...(hint ? { hint } : {})} {...(error ? { error } : {})} />
    </fieldset>
  );
}

export function Checkbox({
  label,
  className,
  ...props
}: Omit<React.ComponentProps<"input">, "type"> & { label: string }) {
  return (
    <label className={cn("flex min-h-11 items-center gap-3 text-sm", className)}>
      <input type="checkbox" className="size-4 shrink-0 accent-primary" {...props} />
      {label}
    </label>
  );
}

/** A form's own outcome: what went wrong (announced at once) or that it saved. */
export function FormOutcome({ failure, saved }: { failure: string | null; saved?: string }) {
  return (
    <>
      {failure === null ? null : (
        <p role="alert" className="text-sm whitespace-pre-line text-destructive">
          {failure}
        </p>
      )}
      <p role="status" className="text-sm text-muted-foreground">
        {saved ?? ""}
      </p>
    </>
  );
}
