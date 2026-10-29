"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/components/auth/problem-message";
import { Turnstile } from "@/components/auth/turnstile";
import { Button } from "@/components/ui/button";
import { Field, Select, Textarea } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { fillBlanks } from "@/lib/content/markdown";
import { z } from "@/lib/forms/zod";
import {
  complain,
  type GrievanceCategory,
  type GrievanceInput,
  type GrievanceReceipt,
} from "@/lib/grievances/client";

export interface GrievanceFormText {
  category: string;
  chooseCategory: string;
  reference: string;
  referenceHint: string;
  details: string;
  detailsHint: string;
  name: string;
  phone: string;
  email: string;
  contactHint: string;
  humanCheck: string;
  submit: string;
  submitting: string;
  needCategory: string;
  needDetails: string;
  tooLong: string;
  needName: string;
  needContact: string;
  badPhone: string;
  badEmail: string;
  receivedTitle: string;
  /** With {ticket}. */
  ticket: string;
  /** With {acknowledgeBy} and {resolveBy}. */
  deadlines: string;
  another: string;
  errors: Record<string, string>;
}

// The API's limits (ADR 0034).
const DETAILS_MAX = 2_000;
const REFERENCE_MAX = 100;
const NAME_MAX = 100;
const EMAIL_MAX = 254;
/** The API takes any token while its human check is off (no Turnstile secret, local and tests). */
const NO_HUMAN_CHECK = "not-checked";
const DATE = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Kolkata",
});

type FieldName = "category" | "reference" | "details" | "name" | "phone" | "email";
const POINTERS: Record<string, FieldName> = {
  "/category": "category",
  "/reference": "reference",
  "/details": "details",
  "/name": "name",
  "/phone": "phone",
  "/email": "email",
};

/**
 * A complaint to the grievance officer (step 3.8, ADR 0034). Anyone may send one: signed out,
 * with a name, a phone number or an email address, and the human check; signed in, the account
 * says who it's from. The ticket number shows at once.
 */
export function GrievanceForm({
  text,
  categories,
  signedIn,
  turnstile,
}: {
  text: GrievanceFormText;
  categories: readonly { value: GrievanceCategory; label: string }[];
  signedIn: boolean;
  turnstile: { siteKey: string; nonce: string | undefined } | undefined;
}) {
  const id = useId();
  const router = useRouter();
  const [receipt, setReceipt] = useState<GrievanceReceipt | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  // A Turnstile token works once: a new widget after each try gives the next one.
  const [widget, setWidget] = useState(0);
  const checking = !signedIn && turnstile !== undefined;

  const schema = z
    .object({
      category: z.string().min(1, text.needCategory),
      reference: z.string().trim().max(REFERENCE_MAX, text.tooLong),
      details: z.string().trim().min(1, text.needDetails).max(DETAILS_MAX, text.tooLong),
      name: z.string().trim().max(NAME_MAX, text.tooLong),
      phone: z.string().trim(),
      email: z.string().trim().max(EMAIL_MAX, text.badEmail),
    })
    .superRefine((values, context) => {
      if (values.phone !== "" && !/^[0-9+()\-\s]{10,20}$/u.test(values.phone)) {
        context.addIssue({ code: "custom", path: ["phone"], message: text.badPhone });
      }
      if (values.email !== "" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/u.test(values.email)) {
        context.addIssue({ code: "custom", path: ["email"], message: text.badEmail });
      }
      if (signedIn) return;
      if (values.name === "") {
        context.addIssue({ code: "custom", path: ["name"], message: text.needName });
      }
      if (values.phone === "" && values.email === "") {
        context.addIssue({ code: "custom", path: ["phone"], message: text.needContact });
      }
    });
  type Values = z.infer<typeof schema>;
  const empty: Values = {
    category: "",
    reference: "",
    details: "",
    name: "",
    phone: "",
    email: "",
  };
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: empty });
  const { errors, isSubmitting } = form.formState;

  async function send(values: Values) {
    setFailure(null);
    const body: GrievanceInput = {
      category: values.category as GrievanceCategory,
      details: values.details,
      reference: values.reference,
      ...(values.name === "" ? {} : { name: values.name }),
      ...(signedIn || values.phone === "" ? {} : { phone: values.phone }),
      ...(values.email === "" ? {} : { email: values.email }),
      humanCheckToken: checking ? (token ?? "") : NO_HUMAN_CHECK,
    };
    try {
      setReceipt(await complain(body));
      form.reset(empty);
      // Signed in, the list of their complaints on this page now has this one.
      if (signedIn) router.refresh();
    } catch (error) {
      setToken(null);
      setWidget((count) => count + 1);
      const fields = error instanceof ApiError ? error.fieldErrors : [];
      let placed = false;
      for (const field of fields) {
        const name = POINTERS[field.pointer ?? ""];
        if (name === undefined) continue;
        placed = true;
        const message =
          name === "phone"
            ? field.code === "missing"
              ? text.needContact
              : text.badPhone
            : name === "email"
              ? text.badEmail
              : name === "name"
                ? text.needName
                : field.detail;
        form.setError(name, { message });
      }
      if (!placed) setFailure(problemMessage(error, text.errors));
    }
  }

  if (receipt !== null) {
    return (
      <div role="status" className="space-y-3 rounded-lg border bg-muted/40 p-5">
        <h3 className="text-lg font-semibold">{text.receivedTitle}</h3>
        <p className="leading-7">{fillBlanks(text.ticket, { ticket: receipt.ticketNumber })}</p>
        <p className="leading-7">
          {fillBlanks(text.deadlines, {
            acknowledgeBy: DATE.format(new Date(receipt.acknowledgeBy)),
            resolveBy: DATE.format(new Date(receipt.resolveBy)),
          })}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setReceipt(null);
          }}
        >
          {text.another}
        </Button>
      </div>
    );
  }

  return (
    <form
      noValidate
      className="space-y-5"
      onSubmit={(event) => {
        void form.handleSubmit(send)(event);
      }}
    >
      <Field id={`${id}-category`} label={text.category} error={errors.category?.message}>
        {(control) => (
          <Select {...control} {...form.register("category")}>
            <option value="">{text.chooseCategory}</option>
            {categories.map((category) => (
              <option key={category.value} value={category.value}>
                {category.label}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field
        id={`${id}-reference`}
        label={text.reference}
        hint={text.referenceHint}
        error={errors.reference?.message}
      >
        {(control) => (
          <Input {...control} maxLength={REFERENCE_MAX} {...form.register("reference")} />
        )}
      </Field>
      <Field
        id={`${id}-details`}
        label={text.details}
        hint={text.detailsHint}
        error={errors.details?.message}
      >
        {(control) => (
          <Textarea {...control} rows={6} maxLength={DETAILS_MAX} {...form.register("details")} />
        )}
      </Field>
      {signedIn ? null : (
        <>
          <Field id={`${id}-name`} label={text.name} error={errors.name?.message}>
            {(control) => (
              <Input
                {...control}
                autoComplete="name"
                maxLength={NAME_MAX}
                {...form.register("name")}
              />
            )}
          </Field>
          <p className="text-sm text-muted-foreground">{text.contactHint}</p>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field id={`${id}-phone`} label={text.phone} error={errors.phone?.message}>
              {(control) => (
                <Input
                  {...control}
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel-national"
                  {...form.register("phone")}
                />
              )}
            </Field>
            <Field id={`${id}-email`} label={text.email} error={errors.email?.message}>
              {(control) => (
                <Input
                  {...control}
                  type="email"
                  autoComplete="email"
                  maxLength={EMAIL_MAX}
                  {...form.register("email")}
                />
              )}
            </Field>
          </div>
          {turnstile === undefined ? null : (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">{text.humanCheck}</p>
              <Turnstile
                key={widget}
                siteKey={turnstile.siteKey}
                action="grievance"
                nonce={turnstile.nonce}
                onToken={setToken}
              />
            </div>
          )}
        </>
      )}
      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
      <Button type="submit" size="lg" disabled={isSubmitting || (checking && token === null)}>
        {isSubmitting ? text.submitting : text.submit}
      </Button>
    </form>
  );
}
