"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { type DefaultValues, type Path, useFieldArray, useForm } from "react-hook-form";

import { problemMessage } from "@/components/auth/problem-message";
import { Button } from "@/components/ui/button";
import { Checkbox, Choices, Field, FormOutcome, Select } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { givePoliceDetails, type TenantDetails } from "@/lib/agreements/client";
import {
  fieldOf,
  GENDERS,
  ID_TYPES,
  MAX_REFERENCES,
  OCCUPATIONS,
  type PoliceFormMessages,
  type PoliceFormValues,
  policeFormSchema,
  toRequest,
} from "@/lib/agreements/police-form";
import { ApiError } from "@/lib/api/errors";
import { showFieldErrors } from "@/lib/forms/field-errors";

export interface PoliceDetailsText {
  title: string;
  intro: string;
  fullName: string;
  parentName: string;
  dateOfBirth: string;
  gender: string;
  genders: Record<(typeof GENDERS)[number], string>;
  phone: string;
  address: string;
  line: string;
  city: string;
  district: string;
  state: string;
  pinCode: string;
  policeStation: string;
  occupation: string;
  occupations: Record<(typeof OCCUPATIONS)[number], string>;
  institution: string;
  idType: string;
  idTypes: Record<(typeof ID_TYPES)[number], string>;
  idLast4: string;
  idLast4Hint: string;
  references: string;
  referencesHint: string;
  referenceName: string;
  referencePhone: string;
  referenceRelation: string;
  addReference: string;
  removeReference: string;
  consent: string;
  save: string;
  saving: string;
  messages: PoliceFormMessages;
  errors: Record<string, string>;
}

/** A person who knows the student: one of their fields, by its form name. */
function reference(index: number, key: "name" | "phone" | "relation"): Path<PoliceFormValues> {
  return `references.${String(index)}.${key}` as Path<PoliceFormValues>;
}

function initial(details: TenantDetails | null): DefaultValues<PoliceFormValues> {
  const address = details?.permanentAddress;
  return {
    fullName: details?.fullName ?? "",
    parentName: details?.parentName ?? "",
    dateOfBirth: details?.dateOfBirth ?? "",
    gender: details?.gender,
    phone: details?.phone ?? "",
    permanentAddress: {
      line: address?.line ?? "",
      city: address?.city ?? "",
      district: address?.district ?? "",
      state: address?.state ?? "",
      pinCode: address?.pinCode ?? "",
      policeStation: address?.policeStation ?? "",
    },
    occupation: details?.occupation,
    institution: details?.institution ?? "",
    idType: details?.idType,
    idLast4: details?.idLast4 ?? "",
    references: (details?.references ?? []).map((item) => ({ ...item })),
    // Asked afresh every time: nothing is pre-ticked (CLAUDE.md rule 7).
    consent: false,
  };
}

/**
 * The student's details for their tenant verification with Delhi Police (ADR 0070): what the
 * police form asks, shown only to the PG's owner, who submits it. An identity document is its type
 * and last four characters only; the owner copies the full number from the original.
 */
export function PoliceDetailsForm({
  code,
  details,
  text,
}: {
  code: string;
  details: TenantDetails | null;
  text: PoliceDetailsText;
}) {
  const id = useId();
  const router = useRouter();
  const [failure, setFailure] = useState<string | null>(null);
  const schema = policeFormSchema(text.messages);
  const form = useForm<PoliceFormValues>({
    resolver: zodResolver(schema),
    defaultValues: initial(details),
  });
  const references = useFieldArray({ control: form.control, name: "references" });
  const { errors, isSubmitting } = form.formState;

  async function save(values: PoliceFormValues) {
    setFailure(null);
    try {
      await givePoliceDetails(code, toRequest(schema.parse(values)));
      router.refresh();
    } catch (error) {
      if (
        showFieldErrors(
          error,
          form.setError,
          (pointer) => fieldOf(pointer) as Path<PoliceFormValues>,
        )
      ) {
        return;
      }
      if (error instanceof ApiError && error.code === "POLICE_DETAILS_INVALID") {
        form.setError("dateOfBirth", { message: error.problem?.detail ?? text.errors.generic });
        return;
      }
      setFailure(problemMessage(error, text.errors));
      if (error instanceof ApiError && error.code === "INVALID_TRANSITION") router.refresh();
    }
  }

  const input = (
    name: Path<PoliceFormValues>,
    label: string,
    extra: object = {},
    hint?: string,
  ) => {
    const error = name
      .split(".")
      .reduce<unknown>(
        (found, key) => (found as Record<string, unknown> | undefined)?.[key],
        errors,
      ) as { message?: string } | undefined;
    return (
      <Field id={`${id}-${name}`} label={label} hint={hint} error={error?.message}>
        {(control) => <Input {...control} {...extra} {...form.register(name)} />}
      </Field>
    );
  };

  return (
    <form
      method="post"
      noValidate
      aria-labelledby={`${id}-title`}
      className="space-y-6 rounded-2xl border border-border/80 bg-background p-5 sm:p-6"
      onSubmit={(event) => {
        void form.handleSubmit(save)(event);
      }}
    >
      <div className="space-y-1.5">
        <h3 id={`${id}-title`} className="font-semibold text-foreground">
          {text.title}
        </h3>
        <p className="text-sm text-muted-foreground">{text.intro}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {input("fullName", text.fullName, { autoComplete: "name", maxLength: 80 })}
        {input("parentName", text.parentName, { maxLength: 80 })}
        {input("dateOfBirth", text.dateOfBirth, { type: "date", autoComplete: "bday" })}
        {input("phone", text.phone, { type: "tel", inputMode: "tel", autoComplete: "tel" })}
      </div>
      <Choices
        id={`${id}-gender`}
        legend={text.gender}
        options={GENDERS.map((value) => ({ value, label: text.genders[value] }))}
        registration={form.register("gender")}
        error={errors.gender?.message}
        columns={3}
      />
      <fieldset className="space-y-4">
        <legend className="text-sm font-semibold text-foreground">{text.address}</legend>
        {input("permanentAddress.line", text.line, {
          autoComplete: "street-address",
          maxLength: 200,
        })}
        <div className="grid gap-4 sm:grid-cols-2">
          {input("permanentAddress.city", text.city, { autoComplete: "address-level2" })}
          {input("permanentAddress.district", text.district)}
          {input("permanentAddress.state", text.state, { autoComplete: "address-level1" })}
          {input("permanentAddress.pinCode", text.pinCode, {
            inputMode: "numeric",
            autoComplete: "postal-code",
            maxLength: 6,
          })}
        </div>
        {input("permanentAddress.policeStation", text.policeStation, { maxLength: 80 })}
      </fieldset>
      <Choices
        id={`${id}-occupation`}
        legend={text.occupation}
        options={OCCUPATIONS.map((value) => ({ value, label: text.occupations[value] }))}
        registration={form.register("occupation")}
        error={errors.occupation?.message}
        columns={3}
      />
      {input("institution", text.institution, { maxLength: 120 })}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id={`${id}-idType`} label={text.idType} error={errors.idType?.message}>
          {(control) => (
            <Select {...control} {...form.register("idType")}>
              <option value="">—</option>
              {ID_TYPES.map((value) => (
                <option key={value} value={value}>
                  {text.idTypes[value]}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {input(
          "idLast4",
          text.idLast4,
          { maxLength: 4, autoComplete: "off", spellCheck: false },
          text.idLast4Hint,
        )}
      </div>
      <fieldset className="space-y-4">
        <legend className="text-sm font-semibold text-foreground">{text.references}</legend>
        <p className="text-sm text-muted-foreground">{text.referencesHint}</p>
        {references.fields.map((item, index) => (
          <div
            key={item.id}
            className="grid gap-4 rounded-xl border border-border/80 p-4 sm:grid-cols-3"
          >
            {input(reference(index, "name"), text.referenceName, { maxLength: 80 })}
            {input(reference(index, "phone"), text.referencePhone, {
              type: "tel",
              inputMode: "tel",
            })}
            {input(reference(index, "relation"), text.referenceRelation, { maxLength: 40 })}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="sm:col-span-3 sm:justify-self-start"
              onClick={() => {
                references.remove(index);
              }}
            >
              <Trash aria-hidden />
              {text.removeReference}
            </Button>
          </div>
        ))}
        {references.fields.length < MAX_REFERENCES ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              references.append({ name: "", phone: "", relation: "" });
            }}
          >
            <Plus aria-hidden />
            {text.addReference}
          </Button>
        ) : null}
      </fieldset>
      <div className="space-y-1">
        <Checkbox
          label={text.consent}
          aria-invalid={errors.consent !== undefined}
          aria-describedby={errors.consent === undefined ? undefined : `${id}-consent-error`}
          {...form.register("consent")}
        />
        {errors.consent?.message === undefined ? null : (
          <p id={`${id}-consent-error`} className="text-sm font-medium text-destructive">
            {errors.consent.message}
          </p>
        )}
      </div>
      <FormOutcome failure={failure} />
      <Button type="submit" size="lg" shape="pill" disabled={isSubmitting}>
        {isSubmitting ? text.saving : text.save}
      </Button>
    </form>
  );
}
