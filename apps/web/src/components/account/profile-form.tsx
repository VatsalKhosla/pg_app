"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { z } from "@/lib/forms/zod";
import { ApiError } from "@/lib/api/errors";
import { type Me, updateProfile } from "@/lib/auth/client";

import { problemMessage } from "../auth/problem-message";

export interface ProfileText {
  name: string;
  nameHint: string;
  nameRequired: string;
  nameTooLong: string;
  place: string;
  placeHint: string;
  placeTooLong: string;
  gender: string;
  genderHint: string;
  genderFemale: string;
  genderMale: string;
  genderOther: string;
  genderUnsaid: string;
  submit: string;
  saving: string;
  saved: string;
  errors: Record<string, string>;
}

type Profile = Pick<Me, "name" | "collegeOrWorkplace" | "gender">;

const NAME_MAX = 80;
const PLACE_MAX = 120;

/** Form fields that the API's problem details point at (`errors[].pointer`). */
const POINTERS = {
  "/name": "name",
  "/collegeOrWorkplace": "collegeOrWorkplace",
  "/gender": "gender",
} as const;

export function ProfileForm({
  text,
  initial,
  onSaved,
}: {
  text: ProfileText;
  initial: Profile;
  onSaved?: (me: Me) => void;
}) {
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const schema = z.object({
    name: z.string().trim().min(1, text.nameRequired).max(NAME_MAX, text.nameTooLong),
    collegeOrWorkplace: z.string().trim().max(PLACE_MAX, text.placeTooLong),
    gender: z.enum(["female", "male", "other", ""]),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: initial.name ?? "",
      collegeOrWorkplace: initial.collegeOrWorkplace ?? "",
      gender: initial.gender ?? "",
    },
  });
  const { errors, isSubmitting } = form.formState;

  async function save(values: Values) {
    setFailure(null);
    setSaved(false);
    try {
      const me = await updateProfile({
        name: values.name,
        collegeOrWorkplace: values.collegeOrWorkplace === "" ? null : values.collegeOrWorkplace,
        gender: values.gender === "" ? null : values.gender,
      });
      setSaved(true);
      onSaved?.(me);
    } catch (error) {
      const fields = error instanceof ApiError ? error.fieldErrors : [];
      let shown = false;
      for (const field of fields) {
        const name =
          field.pointer === undefined
            ? undefined
            : POINTERS[field.pointer as keyof typeof POINTERS];
        if (name !== undefined) {
          form.setError(name, { message: field.detail });
          shown = true;
        }
      }
      if (!shown) setFailure(problemMessage(error, text.errors));
    }
  }

  const genders = [
    { value: "female", label: text.genderFemale },
    { value: "male", label: text.genderMale },
    { value: "other", label: text.genderOther },
    { value: "", label: text.genderUnsaid },
  ] as const;

  return (
    <form
      noValidate
      className="space-y-6"
      onSubmit={(event) => {
        void form.handleSubmit(save)(event);
      }}
    >
      <div className="space-y-2">
        <label htmlFor={`${id}-name`} className="block text-sm font-medium">
          {text.name}
        </label>
        <Input
          id={`${id}-name`}
          autoComplete="name"
          aria-invalid={errors.name !== undefined}
          aria-describedby={`${id}-name-hint${errors.name ? ` ${id}-name-error` : ""}`}
          {...form.register("name")}
        />
        <p id={`${id}-name-hint`} className="text-sm text-muted-foreground">
          {text.nameHint}
        </p>
        {errors.name?.message ? (
          <p id={`${id}-name-error`} className="text-sm text-destructive">
            {errors.name.message}
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <label htmlFor={`${id}-place`} className="block text-sm font-medium">
          {text.place}
        </label>
        <Input
          id={`${id}-place`}
          autoComplete="organization"
          aria-invalid={errors.collegeOrWorkplace !== undefined}
          aria-describedby={`${id}-place-hint${errors.collegeOrWorkplace ? ` ${id}-place-error` : ""}`}
          {...form.register("collegeOrWorkplace")}
        />
        <p id={`${id}-place-hint`} className="text-sm text-muted-foreground">
          {text.placeHint}
        </p>
        {errors.collegeOrWorkplace?.message ? (
          <p id={`${id}-place-error`} className="text-sm text-destructive">
            {errors.collegeOrWorkplace.message}
          </p>
        ) : null}
      </div>

      <fieldset className="space-y-2" aria-describedby={`${id}-gender-hint`}>
        <legend className="text-sm font-medium">{text.gender}</legend>
        <p id={`${id}-gender-hint`} className="text-sm text-muted-foreground">
          {text.genderHint}
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          {genders.map((gender) => (
            <label
              key={gender.value}
              className="flex min-h-11 items-center gap-3 rounded-md border px-3 text-sm has-[:checked]:border-primary has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/50"
            >
              <input
                type="radio"
                value={gender.value}
                className="size-4 accent-primary"
                {...form.register("gender")}
              />
              {gender.label}
            </label>
          ))}
        </div>
      </fieldset>

      {failure === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
      <div className="flex items-center gap-4">
        <Button type="submit" size="lg" disabled={isSubmitting}>
          {isSubmitting ? text.saving : text.submit}
        </Button>
        <p role="status" className="text-sm text-muted-foreground">
          {saved ? text.saved : ""}
        </p>
      </div>
    </form>
  );
}
