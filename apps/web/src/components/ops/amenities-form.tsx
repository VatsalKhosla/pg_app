"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { z } from "@/lib/forms/zod";
import { type Listing, setAmenities } from "@/lib/ops/client";

import { Checkbox, FormOutcome } from "@/components/ui/fields";
import { useOpsProblem } from "./problems";
import { useRefresh } from "./use-refresh";

const schema = z.object({ amenities: z.array(z.string()) });
type Values = z.infer<typeof schema>;

/** What the PG offers, from the API's list (GET /v1/amenities); saving replaces the set. */
export function AmenitiesForm({
  listing,
  amenities,
}: {
  listing: Listing;
  amenities: { slug: string; name: string }[];
}) {
  const t = useTranslations("Ops.amenities");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    // An array, even with one box: React Hook Form then gives back an array of the ticked ones.
    defaultValues: { amenities: listing.amenities },
  });

  async function save({ amenities: chosen }: Values) {
    setFailure(null);
    setSaved(false);
    try {
      await setAmenities(listing.id, chosen);
      form.reset({ amenities: chosen });
      setSaved(true);
      refresh();
    } catch (error) {
      setFailure(problem(error));
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
      <fieldset>
        <legend className="sr-only">{t("title")}</legend>
        <div className="grid gap-x-6 sm:grid-cols-2 lg:grid-cols-3">
          {amenities.map((amenity) => (
            <Checkbox
              key={amenity.slug}
              label={amenity.name}
              value={amenity.slug}
              {...form.register("amenities")}
            />
          ))}
        </div>
      </fieldset>
      <FormOutcome failure={failure} {...(saved ? { saved: t("saved") } : {})} />
      <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? t("saving") : t("save")}
      </Button>
    </form>
  );
}
