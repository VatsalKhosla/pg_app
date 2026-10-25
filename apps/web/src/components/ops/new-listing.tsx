"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useRef, useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { showFieldErrors } from "@/lib/forms/field-errors";
import { z } from "@/lib/forms/zod";
import { createListing, type Owner } from "@/lib/ops/client";

import { FormOutcome } from "./fields";
import {
  type CityChoice,
  type DetailsValues,
  detailsBody,
  detailsDefaults,
  detailsFieldFor,
  detailsShape,
  ListingFields,
  useDetailsMessages,
} from "./listing-fields";
import { OwnerPicker } from "./owner-picker";
import { useOpsProblem } from "./problems";

/** The listing's page, with any listings pinned within 30 m of it to check (ADR 0021). */
function listingPage(id: string, duplicates: readonly string[]): Route {
  const query = new URLSearchParams({ duplicates: duplicates.join(",") }).toString();
  return (
    duplicates.length === 0 ? `/ops/listings/${id}` : `/ops/listings/${id}?${query}`
  ) as Route;
}

/**
 * A new listing's first draft: the owner, the locality and the building. Rooms, photos and
 * amenities follow on the listing's own page, where it goes once it's made.
 */
export function NewListing({ cities }: { cities: CityChoice[] }) {
  const t = useTranslations("Ops");
  const router = useRouter();
  const problem = useOpsProblem();
  const id = useId();
  const ownerRef = useRef<HTMLHeadingElement>(null);
  const [owner, setOwner] = useState<Owner | null>(null);
  const [ownerMissing, setOwnerMissing] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const messages = useDetailsMessages();
  const form = useForm<DetailsValues>({
    resolver: zodResolver(z.object(detailsShape(messages))),
    defaultValues: detailsDefaults(),
  });

  async function create(values: DetailsValues) {
    setFailure(null);
    if (owner === null) {
      setOwnerMissing(true);
      ownerRef.current?.focus();
      return;
    }
    try {
      const created = await createListing({
        owner: owner.id,
        locality: values.locality,
        ...detailsBody(values),
      });
      router.push(listingPage(created.id, created.possibleDuplicates));
    } catch (error) {
      if (!showFieldErrors(error, form.setError, detailsFieldFor)) setFailure(problem(error));
    }
  }

  // The owner has its own search and form, so it sits outside the listing's form.
  return (
    <div className="space-y-10">
      <section aria-labelledby={`${id}-owner`} className="space-y-4">
        <h2 id={`${id}-owner`} ref={ownerRef} tabIndex={-1} className="text-lg font-semibold">
          {t("owner.legend")}
        </h2>
        <OwnerPicker
          owner={owner}
          onOwner={(chosen) => {
            setOwner(chosen);
            if (chosen !== null) setOwnerMissing(false);
          }}
          missing={ownerMissing}
        />
      </section>

      <section aria-labelledby={`${id}-details`} className="space-y-4">
        <h2 id={`${id}-details`} className="text-lg font-semibold">
          {t("details.title")}
        </h2>
        <form
          noValidate
          className="space-y-6"
          onSubmit={(event) => {
            void form.handleSubmit(create)(event);
          }}
        >
          <ListingFields form={form} cities={cities} />
          <FormOutcome failure={failure} />
          <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t("new.creating") : t("new.create")}
          </Button>
        </form>
      </section>
    </div>
  );
}
