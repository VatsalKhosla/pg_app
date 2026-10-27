"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { showFieldErrors } from "@/lib/forms/field-errors";
import { z } from "@/lib/forms/zod";
import { type Owner, updateOwner } from "@/lib/ops/client";

import { Field, FormOutcome } from "./fields";
import { GSTIN_MAX, NAME_MAX } from "./owner-picker";
import { useOpsProblem } from "./problems";
import { useRefresh } from "./use-refresh";

const FIELDS = ["legalName", "businessName", "gstin"] as const;

/** An owner's business details; only what ops changed is sent, and an empty GSTIN clears it. */
export function OwnerForm({ owner }: { owner: Owner }) {
  const t = useTranslations("Ops");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const required = t("validation.required");
  const tooLong = t("validation.tooLong");
  const schema = z.object({
    legalName: z.string().trim().min(1, required).max(NAME_MAX, tooLong),
    businessName: z.string().trim().min(1, required).max(NAME_MAX, tooLong),
    gstin: z.string().trim().max(GSTIN_MAX, tooLong),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      legalName: owner.legalName,
      businessName: owner.businessName,
      gstin: owner.gstin ?? "",
    },
  });
  const { errors, isSubmitting, dirtyFields } = form.formState;

  async function save(values: Values) {
    setFailure(null);
    setSaved(false);
    try {
      const changes = {
        ...(dirtyFields.legalName ? { legalName: values.legalName } : {}),
        ...(dirtyFields.businessName ? { businessName: values.businessName } : {}),
        ...(dirtyFields.gstin ? { gstin: values.gstin === "" ? null : values.gstin } : {}),
      };
      if (Object.keys(changes).length > 0) await updateOwner(owner.id, changes);
      // What was saved is the new starting point, so the next save sends only what changes next.
      form.reset(values);
      setSaved(true);
      refresh();
    } catch (error) {
      const shown = showFieldErrors(error, form.setError, (pointer) =>
        FIELDS.find((field) => pointer === `/${field}`),
      );
      if (!shown) setFailure(problem(error));
    }
  }

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(event) => {
        void form.handleSubmit(save)(event);
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
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
      <FormOutcome failure={failure} {...(saved ? { saved: t("ownerPage.saved") } : {})} />
      <Button type="submit" size="lg" disabled={isSubmitting}>
        {isSubmitting ? t("ownerPage.saving") : t("ownerPage.save")}
      </Button>
    </form>
  );
}
