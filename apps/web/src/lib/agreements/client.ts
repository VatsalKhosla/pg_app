import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * Rent agreements and police verification from the browser (ADR 0070): asking for a signing code,
 * signing, the student's police-verification details, and the owner's submission. Pages read on
 * the server (./server.ts).
 */

export type RentAgreement = Schemas["RentAgreement"];
export type OpsRentAgreement = Schemas["OpsRentAgreement"];
export type Side = RentAgreement["you"];
export type SigningCodeSent = Schemas["SigningCodeSent"];
export type SignatureRequest = Schemas["SignatureRequest"];
export type TenantDetails = Schemas["TenantDetails"];
export type TenantDetailsInput = Schemas["TenantDetailsInput"];
export type StudentPoliceVerification = Schemas["StudentPoliceVerification"];
export type OwnerPoliceVerification = Schemas["OwnerPoliceVerification"];
export type OpsPoliceVerification = Schemas["OpsPoliceVerification"];
export type PoliceStatus = StudentPoliceVerification["status"];

/** A code for the signer to sign with, sent to them; ten minutes, and a new one replaces it. */
export function askForSigningCode(side: Side, code: string): Promise<SigningCodeSent> {
  return withCsrf((headers) => {
    const init = { params: { path: { code } }, headers };
    return unwrap(
      side === "student"
        ? browserApi.POST("/v1/bookings/{code}/agreement/signing-codes", init)
        : browserApi.POST("/v1/owner/bookings/{code}/agreement/signing-codes", init),
    );
  });
}

/** Sign with the code, the full name and the hash of the text read; refused if it changed. */
export function signAgreement(
  side: Side,
  code: string,
  body: SignatureRequest,
): Promise<RentAgreement> {
  return withCsrf((headers) => {
    const init = { params: { path: { code } }, body, headers };
    return unwrap(
      side === "student"
        ? browserApi.POST("/v1/bookings/{code}/agreement/signatures", init)
        : browserApi.POST("/v1/owner/bookings/{code}/agreement/signatures", init),
    );
  });
}

/** The student's details for the police form, given or corrected until the owner submits them. */
export function givePoliceDetails(
  code: string,
  body: TenantDetailsInput,
): Promise<StudentPoliceVerification> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.PUT("/v1/bookings/{code}/police-verification", {
        params: { path: { code } },
        body,
        headers,
      }),
    ),
  );
}

/** The owner submitted the details on the police portal: the acknowledgement they uploaded. */
export function markSubmitted(
  code: string,
  body: Schemas["PoliceSubmission"],
): Promise<OwnerPoliceVerification> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/owner/bookings/{code}/police-verification/mark-submitted", {
        params: { path: { code } },
        body,
        headers,
      }),
    ),
  );
}

/** The police have verified the tenant, as the owner says. */
export function markVerified(code: string): Promise<OwnerPoliceVerification> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/owner/bookings/{code}/police-verification/mark-verified", {
        params: { path: { code } },
        headers,
      }),
    ),
  );
}
