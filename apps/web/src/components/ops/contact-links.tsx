import { Fragment } from "react";

/**
 * How staff reach someone: a call link for their phone and a mail link for their address, each
 * after a " · ". An account has a phone, an address or both (ADR 0068); a missing one shows
 * nothing, never an empty link.
 */
export function ContactLinks({
  phone,
  email,
}: {
  phone: string | null;
  email?: string | null | undefined;
}) {
  const links = [
    ...(phone === null ? [] : [{ href: `tel:${phone}`, label: phone }]),
    ...(email == null ? [] : [{ href: `mailto:${email}`, label: email }]),
  ];
  return links.map((link) => (
    <Fragment key={link.href}>
      {" · "}
      <a
        href={link.href}
        className="font-medium break-all text-primary underline underline-offset-4"
      >
        {link.label}
      </a>
    </Fragment>
  ));
}
