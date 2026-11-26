/** An Indian number in E.164 (+91 and ten digits) as people read it, "+91 98910 02696"; any
 * other number as it is. */
export function formatPhone(e164: string): string {
  if (!/^\+91\d{10}$/u.test(e164)) return e164;
  return `+91 ${e164.slice(3, 8)} ${e164.slice(8)}`;
}
