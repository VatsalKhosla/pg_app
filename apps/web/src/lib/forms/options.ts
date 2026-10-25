/**
 * Every value of a union, from a record keyed by each of them: the compiler refuses the record if
 * one is missing, so a form's choices can't fall behind the API's enum.
 */
export function valuesOf<T extends string>(record: Record<T, true>): [T, ...T[]] {
  return Object.keys(record) as [T, ...T[]];
}
