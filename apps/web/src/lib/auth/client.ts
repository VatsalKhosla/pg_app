import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

export type ChallengeIssued = Schemas["OtpChallengeIssued"];
export type SignInResult = Schemas["SignInResult"];
export type StaffSignInResult = Schemas["StaffSignInResult"];
export type PrivacyNotice = Schemas["PrivacyNoticeInfo"];
export type ConsentInput = Schemas["ConsentInput"];
export type ProfileChanges = Schemas["MeUpdate"];
export type Me = Schemas["Me"];

/**
 * Sign-in and account calls from the browser. The browser talks to the API itself, so the
 * API's own cookies (the session and the CSRF token) are set and sent without the web server.
 * State-changing calls carry the CSRF token (ADR 0014), read from its cookie or fetched.
 */

export function requestCode(phone: string, humanCheckToken: string): Promise<ChallengeIssued> {
  return withCsrf((headers) =>
    unwrap(browserApi.POST("/v1/auth/otp/request", { body: { phone, humanCheckToken }, headers })),
  );
}

export function verifyCode(
  challengeId: string,
  code: string,
  consent?: ConsentInput,
): Promise<SignInResult> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/auth/otp/verify", {
        body: { challengeId, code, ...(consent === undefined ? {} : { consent }) },
        headers,
      }),
    ),
  );
}

export function signInWithAuthenticator(code: string): Promise<StaffSignInResult> {
  return withCsrf((headers) =>
    unwrap(browserApi.POST("/v1/auth/staff/totp", { body: { code }, headers })),
  );
}

export function privacyNotice(): Promise<PrivacyNotice> {
  return unwrap(browserApi.GET("/v1/privacy-notice"));
}

export function updateProfile(changes: ProfileChanges): Promise<Me> {
  return withCsrf((headers) => unwrap(browserApi.PATCH("/v1/me", { body: changes, headers })));
}

export function signOut(): Promise<void> {
  return withCsrf((headers) => unwrap(browserApi.POST("/v1/auth/logout", { headers })));
}

export type DataRequest = Schemas["DataRequestInfo"];

export function askForData(kind: "export" | "deletion"): Promise<DataRequest> {
  return withCsrf((headers) =>
    unwrap(browserApi.POST("/v1/me/data-requests", { body: { kind }, headers })),
  );
}

export async function agreeToNotice(noticeVersion: string): Promise<void> {
  await withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/me/consents", {
        body: { noticeVersion, purposes: ["account"] },
        headers,
      }),
    ),
  );
}

/** Opt in to, or out of, offers and news (the optional `marketing` purpose). */
export async function setMarketingConsent(on: boolean, noticeVersion: string): Promise<void> {
  await withCsrf((headers) =>
    on
      ? unwrap(
          browserApi.POST("/v1/me/consents", {
            body: { noticeVersion, purposes: ["marketing"] },
            headers,
          }),
        )
      : unwrap(
          browserApi.DELETE("/v1/me/consents/{purpose}", {
            params: { path: { purpose: "marketing" } },
            headers,
          }),
        ),
  );
}
