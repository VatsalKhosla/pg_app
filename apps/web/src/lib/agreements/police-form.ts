import type { TenantDetailsInput } from "@/lib/agreements/client";
import { z } from "@/lib/forms/zod";

/**
 * The student's police-verification form (ADR 0070), checked in the browser as the API checks it:
 * the API decides, and its errors show by their fields too.
 *
 * **No Aadhaar numbers.** An identity document is its type and its last four characters only, and
 * any text that holds what looks like an Aadhaar number (twelve digits, spaced or not, in any
 * script's digits) is refused, whichever field it was typed into.
 */

const AADHAAR_LIKE = /\p{Nd}{4}[ .-]?\p{Nd}{4}[ .-]?\p{Nd}{4}/u;
const PHONE = /^(?:\+?91|0)?[6-9]\d{9}$/u;
const PIN = /^[1-9]\d{5}$/u;
const LAST_FOUR = /^[A-Za-z0-9]{4}$/u;
const DIGITS = /^\d{4}$/u;

export const GENDERS = ["female", "male", "other"] as const;
export const OCCUPATIONS = ["student", "working", "other"] as const;
export const ID_TYPES = ["aadhaar", "passport", "voter_id", "driving_licence", "pan"] as const;
export const MAX_REFERENCES = 2;

export function holdsAadhaarLikeNumber(text: string): boolean {
  return AADHAAR_LIKE.test(text);
}

export interface PoliceFormMessages {
  required: string;
  aadhaar: string;
  phone: string;
  pin: string;
  last4: string;
  aadhaarLast4: string;
  consent: string;
}

export function policeFormSchema(m: PoliceFormMessages) {
  const text = (min: number, max: number) =>
    z
      .string()
      .trim()
      .min(min, m.required)
      .max(max, m.required)
      .refine((value) => !holdsAadhaarLikeNumber(value), m.aadhaar);
  const phone = z
    .string()
    .trim()
    .refine((value) => PHONE.test(value.replaceAll(/[\s().-]/gu, "")), m.phone);
  return z
    .object({
      fullName: text(2, 80),
      parentName: text(2, 80),
      dateOfBirth: z.string().regex(/^\d{4}-\d{2}-\d{2}$/u, m.required),
      gender: z.enum(GENDERS, { error: m.required }),
      phone,
      permanentAddress: z.object({
        line: text(2, 200),
        city: text(2, 80),
        district: text(2, 80),
        state: text(2, 80),
        pinCode: z.string().trim().regex(PIN, m.pin),
        policeStation: z
          .string()
          .trim()
          .max(80, m.required)
          .refine((value) => !holdsAadhaarLikeNumber(value), m.aadhaar),
      }),
      occupation: z.enum(OCCUPATIONS, { error: m.required }),
      institution: text(2, 120),
      idType: z.enum(ID_TYPES, { error: m.required }),
      idLast4: z.string().trim().regex(LAST_FOUR, m.last4),
      references: z
        .array(z.object({ name: text(2, 80), phone, relation: text(2, 40) }))
        .max(MAX_REFERENCES),
      // Ticked by the student, never pre-ticked (CLAUDE.md rule 7).
      consent: z.boolean().refine((value) => value, m.consent),
    })
    .superRefine((values, context) => {
      if (values.idType === "aadhaar" && !DIGITS.test(values.idLast4)) {
        context.addIssue({ code: "custom", path: ["idLast4"], message: m.aadhaarLast4 });
      }
    });
}

export type PoliceFormValues = z.input<ReturnType<typeof policeFormSchema>>;

/** The form's values as the API takes them: an empty police station is none. */
export function toRequest(
  values: z.output<ReturnType<typeof policeFormSchema>>,
): TenantDetailsInput {
  const { policeStation, ...address } = values.permanentAddress;
  return {
    ...values,
    consent: true,
    permanentAddress: policeStation === "" ? address : { ...address, policeStation },
  };
}

/** The form field an API error's JSON pointer is about ("/permanentAddress/pinCode"), if any. */
export function fieldOf(pointer: string): string | undefined {
  const path = pointer.replace(/^\//u, "").replaceAll("/", ".");
  return /^(?:fullName|parentName|dateOfBirth|gender|phone|occupation|institution|idType|idLast4|consent|permanentAddress\.(?:line|city|district|state|pinCode|policeStation)|references\.[01]\.(?:name|phone|relation))$/u.test(
    path,
  )
    ? path
    : undefined;
}
