"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { showFieldErrors } from "@/lib/forms/field-errors";
import { z } from "@/lib/forms/zod";
import { type Listing, updateListing } from "@/lib/ops/client";

import { FormOutcome } from "@/components/ui/fields";
import {
  changedDetails,
  type DetailsValues,
  detailsDefaults,
  detailsFieldFor,
  detailsShape,
  ListingFields,
  useDetailsMessages,
} from "./listing-fields";
import { useOpsProblem } from "./problems";
import { useRefresh } from "./use-refresh";

/** A listing's details, saved as a whole; only the fields ops changed are sent. */
export function DetailsForm({ listing }: { listing: Listing }) {
  const t = useTranslations("Ops.details");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const messages = useDetailsMessages();
  const form = useForm<DetailsValues>({
    resolver: zodResolver(z.object(detailsShape(messages))),
    defaultValues: detailsDefaults(listing),
  });

  async function save(values: DetailsValues) {
    setFailure(null);
    setSaved(false);
    const changes = changedDetails(values, form.formState.dirtyFields);
    try {
      if (Object.keys(changes).length > 0) await updateListing(listing.id, changes);
      // What was saved is the new starting point, so the next save sends only what changes next.
      form.reset(values);
      setSaved(true);
      refresh();
    } catch (error) {
      if (!showFieldErrors(error, form.setError, detailsFieldFor)) setFailure(problem(error));
    }
  }

  return (
    <form
      noValidate
      className="space-y-6"
      onSubmit={(event) => {
        void form.handleSubmit(save)(event);
      }}
    >
      <ListingFields form={form} />
      <FormOutcome failure={failure} {...(saved ? { saved: t("saved") } : {})} />
      <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? t("saving") : t("save")}
      </Button>
    </form>
  );
}
