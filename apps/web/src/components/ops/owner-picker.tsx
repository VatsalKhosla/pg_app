"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { showFieldErrors } from "@/lib/forms/field-errors";
import { z } from "@/lib/forms/zod";
import { addOwner, findOwners, type Owner } from "@/lib/ops/client";

import { Field, FormOutcome } from "@/components/ui/fields";
import { useOpsProblem } from "./problems";

/** The API's limits for owners (apps/api/src/app/modules/catalog/domain/owners.py). */
export const NAME_MAX = 120;
export const GSTIN_MAX = 20;
const SEARCH_MAX = 100;

const OWNER_FIELDS = ["phone", "name", "legalName", "businessName", "gstin"] as const;

/**
 * Who owns the PG: found by their phone number or business name, or added here. Adding an owner
 * makes their account if they've never signed in; they sign in with that number later.
 */
export function OwnerPicker({
  owner,
  onOwner,
  missing,
}: {
  owner: Owner | null;
  onOwner: (owner: Owner | null) => void;
  /** The listing was submitted without one. */
  missing: boolean;
}) {
  const t = useTranslations("Ops.owner");
  const problem = useOpsProblem();
  const id = useId();
  const [results, setResults] = useState<Owner[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const search = useForm({
    resolver: zodResolver(
      z.object({ q: z.string().trim().min(1, t("searchRequired")).max(SEARCH_MAX) }),
    ),
    defaultValues: { q: "" },
  });

  async function find({ q }: { q: string }) {
    setFailure(null);
    try {
      setResults((await findOwners(q)).items);
    } catch (error) {
      setFailure(problem(error));
    }
  }

  if (owner !== null) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-4">
        <p className="text-sm">
          {t("chosen", { business: owner.businessName, phone: owner.phone ?? "" })}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            onOwner(null);
          }}
        >
          {t("change")}
        </Button>
      </div>
    );
  }

  const searchError = search.formState.errors.q?.message;
  return (
    <div className="space-y-6">
      <form
        noValidate
        role="search"
        className="space-y-3"
        onSubmit={(event) => {
          void search.handleSubmit(find)(event);
        }}
      >
        <Field id={`${id}-q`} label={t("search")} error={searchError}>
          {(control) => (
            <div className="flex gap-2">
              <Input {...control} type="search" autoComplete="off" {...search.register("q")} />
              <Button
                type="submit"
                variant="secondary"
                size="lg"
                disabled={search.formState.isSubmitting}
              >
                {search.formState.isSubmitting ? t("searching") : t("searchButton")}
              </Button>
            </div>
          )}
        </Field>
        <FormOutcome failure={failure} />
      </form>

      <div aria-live="polite">
        {results === null ? null : results.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("none")}</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {results.map((found) => (
              <li key={found.id} className="flex flex-wrap items-center justify-between gap-3 p-3">
                <div className="min-w-0">
                  <p className="font-medium">{found.businessName}</p>
                  <p className="text-sm text-muted-foreground">
                    {found.legalName}
                    {found.phone === null ? null : ` · ${found.phone}`}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    onOwner(found);
                  }}
                >
                  {t("choose", { business: found.businessName })}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {missing ? (
        <p role="alert" className="text-sm text-destructive">
          {t("required")}
        </p>
      ) : null}

      <section aria-labelledby={`${id}-add`} className="space-y-4 rounded-md border p-4">
        <h3 id={`${id}-add`} className="font-medium">
          {t("addTitle")}
        </h3>
        <AddOwner onAdded={onOwner} />
      </section>
    </div>
  );
}

/** A new owner, by their phone number and business names. */
export function AddOwner({ onAdded }: { onAdded: (owner: Owner) => void }) {
  const t = useTranslations("Ops");
  const problem = useOpsProblem();
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const required = t("validation.required");
  const tooLong = t("validation.tooLong");
  const schema = z.object({
    // The API decides what an Indian mobile number is; this only catches slips.
    phone: z
      .string()
      .trim()
      .regex(/^[0-9+()\-\s]{10,20}$/u, t("owner.phoneInvalid")),
    name: z.string().trim().max(NAME_MAX, tooLong),
    legalName: z.string().trim().min(1, required).max(NAME_MAX, tooLong),
    businessName: z.string().trim().min(1, required).max(NAME_MAX, tooLong),
    gstin: z.string().trim().max(GSTIN_MAX, tooLong),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { phone: "", name: "", legalName: "", businessName: "", gstin: "" },
  });
  const { errors, isSubmitting } = form.formState;

  async function add(values: Values) {
    setFailure(null);
    try {
      onAdded(
        await addOwner({
          phone: values.phone,
          legalName: values.legalName,
          businessName: values.businessName,
          gstin: values.gstin === "" ? null : values.gstin,
          name: values.name === "" ? null : values.name,
        }),
      );
    } catch (error) {
      const shown = showFieldErrors(error, form.setError, (pointer) =>
        OWNER_FIELDS.find((field) => pointer === `/${field}`),
      );
      if (!shown) setFailure(problem(error));
    }
  }

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(event) => {
        void form.handleSubmit(add)(event);
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id={`${id}-phone`} label={t("owner.phone")} error={errors.phone?.message}>
          {(control) => (
            <Input {...control} type="tel" autoComplete="off" {...form.register("phone")} />
          )}
        </Field>
        <Field id={`${id}-name`} label={t("owner.name")} error={errors.name?.message}>
          {(control) => <Input {...control} autoComplete="off" {...form.register("name")} />}
        </Field>
        <Field id={`${id}-legal`} label={t("owner.legalName")} error={errors.legalName?.message}>
          {(control) => <Input {...control} autoComplete="off" {...form.register("legalName")} />}
        </Field>
        <Field
          id={`${id}-business`}
          label={t("owner.businessName")}
          error={errors.businessName?.message}
        >
          {(control) => (
            <Input {...control} autoComplete="off" {...form.register("businessName")} />
          )}
        </Field>
        <Field id={`${id}-gstin`} label={t("owner.gstin")} error={errors.gstin?.message}>
          {(control) => (
            <Input
              {...control}
              autoComplete="off"
              autoCapitalize="characters"
              {...form.register("gstin")}
            />
          )}
        </Field>
      </div>
      <FormOutcome failure={failure} />
      <Button type="submit" variant="secondary" size="lg" disabled={isSubmitting}>
        {isSubmitting ? t("owner.adding") : t("owner.add")}
      </Button>
    </form>
  );
}
