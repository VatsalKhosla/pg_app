import type * as React from "react";
import type { UseFormRegisterReturn } from "react-hook-form";

import { cn } from "@/lib/utils";

import { controlClasses } from "./input";

/**
 * Form controls: a label, the control, a hint and the field's error, wired together for screen
 * readers (aria-describedby, aria-invalid).
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
        <p id={`${id}-error`} className="text-sm font-medium text-destructive">
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

/** A native select (the phone's own picker), drawn like the other controls. */
export function Select({ className, ...props }: React.ComponentProps<"select">) {
  return <select className={cn(controlClasses, "h-11 pointer-fine:h-10", className)} {...props} />;
}

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return <textarea className={cn(controlClasses, "min-h-24 py-2.5", className)} {...props} />;
}

/**
 * A group of radio buttons, each a large target drawn as a card: the chosen one takes the brand
 * colour, with a thicker border so the choice doesn't rest on colour alone (WCAG 1.4.1).
 */
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
            className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-input px-3.5 text-sm transition-[color,background-color,border-color,box-shadow] duration-(--duration-fast) ease-standard hover:border-foreground/60 has-[:checked]:border-primary has-[:checked]:bg-primary-soft has-[:checked]:font-medium has-[:checked]:ring-1 has-[:checked]:ring-primary has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring motion-reduce:transition-none"
          >
            <input
              type="radio"
              value={option.value}
              className="size-[1.125rem] shrink-0 accent-primary outline-none"
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
    <label className={cn("flex min-h-11 cursor-pointer items-center gap-3 text-sm", className)}>
      <input type="checkbox" className="size-[1.125rem] shrink-0 accent-primary" {...props} />
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
