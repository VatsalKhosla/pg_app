import "server-only";

import { getTranslations } from "next-intl/server";

import type { ProfileText } from "@/components/account/profile-form";
import { brand } from "@/config/brand";

import type { SignInText } from "./sign-in-flow";

/** The API's error codes the sign-in and profile forms explain (ARCHITECTURE §15). */
const ERROR_CODES = [
  "OTP_INVALID",
  "OTP_EXPIRED",
  "OTP_LOCKED",
  "OTP_RESEND_TOO_SOON",
  "RATE_LIMITED",
  "HUMAN_CHECK_FAILED",
  "ACCOUNT_SUSPENDED",
  "PRIVACY_NOTICE_CHANGED",
  "SERVICE_UNAVAILABLE",
  "API_UNREACHABLE",
  "API_TIMEOUT",
  "TOTP_INVALID",
  "STAFF_ACCOUNT_NOT_ALLOWED",
  "CSRF_TOKEN_INVALID",
  "VALIDATION_ERROR",
] as const;

/** Error messages by code, with the general one as `generic`. */
export async function errorText(): Promise<Record<string, string>> {
  const t = await getTranslations("AuthErrors");
  return {
    generic: t("generic"),
    ...Object.fromEntries(ERROR_CODES.map((code) => [code, t(code)])),
  };
}

export async function profileText(): Promise<ProfileText> {
  const t = await getTranslations("Profile");
  return {
    name: t("name"),
    nameHint: t("nameHint"),
    nameRequired: t("nameRequired"),
    nameTooLong: t("nameTooLong"),
    place: t("place"),
    placeHint: t("placeHint"),
    placeTooLong: t("placeTooLong"),
    gender: t("gender"),
    genderHint: t("genderHint"),
    genderFemale: t("genderFemale"),
    genderMale: t("genderMale"),
    genderOther: t("genderOther"),
    genderUnsaid: t("genderUnsaid"),
    submit: t("submit"),
    saving: t("saving"),
    saved: t("saved"),
    errors: await errorText(),
  };
}

/** Every string the sign-in flow shows, translated here so the browser needs no formatter. */
export async function signInText(): Promise<SignInText> {
  const t = await getTranslations("SignIn");
  return {
    phone: {
      title: t("phone.title"),
      intro: t("phone.intro"),
      label: t("phone.label"),
      hint: t("phone.hint"),
      invalid: t("phone.invalid"),
      humanCheck: t("phone.humanCheck"),
      submit: t("phone.submit"),
      sending: t("phone.sending"),
    },
    code: {
      title: t("code.title"),
      // The number is filled in by the browser, which knows it.
      intro: t.raw("code.intro") as string,
      // So is the code, when local development shows it (no text message is sent there).
      developmentCode: t.raw("code.developmentCode") as string,
      label: t("code.label"),
      invalid: t("code.invalid"),
      submit: t("code.submit"),
      checking: t("code.checking"),
      resend: t("code.resend"),
      resendLater: t("code.resendLater"),
      otherNumber: t("code.otherNumber"),
    },
    consent: {
      title: t("consent.title"),
      intro: t("consent.intro"),
      notice: t("consent.notice"),
      account: t("consent.account", { brand: brand.name }),
      accountRequired: t("consent.accountRequired"),
      marketing: t("consent.marketing"),
      submit: t("consent.submit"),
    },
    profile: {
      title: t("profile.title"),
      intro: t("profile.intro"),
      form: await profileText(),
    },
    authenticator: {
      title: t("authenticator.title"),
      intro: t("authenticator.intro", { brand: brand.name }),
      label: t("authenticator.label"),
      invalid: t("authenticator.invalid"),
      submit: t("authenticator.submit"),
      checking: t("authenticator.checking"),
    },
    errors: await errorText(),
  };
}
