import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "@/lib/api/errors";

/**
 * Put the API's field errors (problem details' `errors[]`, by JSON pointer) next to the fields
 * they're about. `fieldFor` names the form field for a pointer, or undefined for one the form
 * doesn't show. Returns whether any error was placed; the caller shows the rest as the form's own.
 */
export function showFieldErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fieldFor: (pointer: string) => Path<T> | undefined,
): boolean {
  if (!(error instanceof ApiError)) return false;
  let shown = false;
  for (const field of error.fieldErrors) {
    const name = typeof field.pointer === "string" ? fieldFor(field.pointer) : undefined;
    if (name !== undefined) {
      setError(name, { message: field.detail });
      shown = true;
    }
  }
  return shown;
}
