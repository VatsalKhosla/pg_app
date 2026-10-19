"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import type { Route } from "next";
import { useEffect, useId, useRef, useState } from "react";
import { useForm } from "react-hook-form";

import { ProfileForm, type ProfileText } from "@/components/account/profile-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { z } from "@/lib/forms/zod";
import { ApiError } from "@/lib/api/errors";
import {
  type ChallengeIssued,
  type ConsentInput,
  type Me,
  type PrivacyNotice,
  privacyNotice,
  requestCode,
  signInWithAuthenticator,
  verifyCode,
} from "@/lib/auth/client";

import { problemMessage } from "./problem-message";
import { Turnstile } from "./turnstile";

export interface SignInText {
  phone: {
    title: string;
    intro: string;
    label: string;
    hint: string;
    invalid: string;
    humanCheck: string;
    submit: string;
    sending: string;
  };
  code: {
    title: string;
    intro: string;
    label: string;
    invalid: string;
    submit: string;
    checking: string;
    resend: string;
    resendLater: string;
    otherNumber: string;
  };
  consent: {
    title: string;
    intro: string;
    notice: string;
    account: string;
    accountRequired: string;
    marketing: string;
    submit: string;
  };
  profile: { title: string; intro: string; form: ProfileText };
  authenticator: {
    title: string;
    intro: string;
    label: string;
    invalid: string;
    submit: string;
    checking: string;
  };
  errors: Record<string, string>;
}

/** The API takes any token while its human check is off (no Turnstile secret, local and tests). */
const NO_HUMAN_CHECK = "not-checked";
const MAX_RESEND_WAIT_MS = 120_000;

type Step =
  | { name: "phone"; phone: string; notice?: string }
  | { name: "code"; phone: string; challenge: ChallengeIssued }
  | {
      name: "consent";
      phone: string;
      challenge: ChallengeIssued;
      code: string;
      notice: PrivacyNotice;
    }
  | { name: "profile"; me: Me }
  | { name: "authenticator" };

/**
 * Signing in by phone: the number, the code sent to it, consent if this makes a new account (the
 * API says so), then the profile for new people, or the authenticator code for staff. Finishing
 * loads `next` afresh, so every part of the page sees the new session.
 */
export function SignInFlow({
  text,
  next,
  mode,
  turnstile,
}: {
  text: SignInText;
  next: Route;
  /** "staff" asks for the authenticator code after the phone code. */
  mode: "people" | "staff";
  turnstile?: { siteKey: string; nonce: string | undefined } | undefined;
}) {
  const [step, setStep] = useState<Step>({ name: "phone", phone: "" });
  const heading = useRef<HTMLHeadingElement>(null);
  const first = useRef(true);
  useEffect(() => {
    // Moving focus to each new step's heading tells screen reader users where they are.
    if (first.current) first.current = false;
    else heading.current?.focus();
  }, [step.name]);

  function finish() {
    // A full load, so the root layout's header renders with the new session too (client
    // navigation keeps layouts as they were).
    window.location.assign(next);
  }

  function signedIn(me: Me) {
    if (mode === "staff") setStep({ name: "authenticator" });
    else if (me.name === null) setStep({ name: "profile", me });
    else finish();
  }

  const titles = {
    phone: text.phone,
    code: text.code,
    consent: text.consent,
    profile: text.profile,
    authenticator: text.authenticator,
  };
  const current = titles[step.name];

  return (
    <section aria-labelledby="sign-in-step" className="space-y-6">
      <div className="space-y-2">
        <h2
          id="sign-in-step"
          ref={heading}
          tabIndex={-1}
          className="text-xl font-semibold tracking-tight outline-none"
        >
          {current.title}
        </h2>
        <p className="text-muted-foreground">
          {step.name === "code" ? current.intro.replace("{phone}", step.phone) : current.intro}
        </p>
      </div>
      {step.name === "phone" ? (
        <PhoneStep
          text={text}
          defaultPhone={step.phone}
          notice={step.notice}
          turnstile={turnstile}
          onSent={(phone, challenge) => {
            setStep({ name: "code", phone, challenge });
          }}
        />
      ) : null}
      {step.name === "code" ? (
        <CodeStep
          text={text}
          challenge={step.challenge}
          onSignedIn={signedIn}
          onConsentNeeded={(code, notice) => {
            setStep({ ...step, name: "consent", code, notice });
          }}
          onRestart={(notice) => {
            setStep({ name: "phone", phone: step.phone, notice });
          }}
        />
      ) : null}
      {step.name === "consent" ? (
        <ConsentStep
          text={text}
          notice={step.notice}
          onAgree={async (consent) => {
            try {
              signedIn((await verifyCode(step.challenge.challengeId, step.code, consent)).user);
              return null;
            } catch (error) {
              if (
                error instanceof ApiError &&
                ["OTP_EXPIRED", "OTP_INVALID"].includes(error.code)
              ) {
                setStep({ name: "phone", phone: step.phone, notice: text.errors.OTP_EXPIRED });
                return null;
              }
              if (error instanceof ApiError && error.code === "PRIVACY_NOTICE_CHANGED") {
                setStep({ ...step, notice: await privacyNotice() });
              }
              return problemMessage(error, text.errors);
            }
          }}
        />
      ) : null}
      {step.name === "profile" ? (
        <ProfileForm text={text.profile.form} initial={step.me} onSaved={finish} />
      ) : null}
      {step.name === "authenticator" ? <AuthenticatorStep text={text} onDone={finish} /> : null}
    </section>
  );
}

function FieldError({ id, message }: { id: string; message: string | undefined }) {
  return message ? (
    <p id={id} className="text-sm text-destructive">
      {message}
    </p>
  ) : null;
}

function FormFailure({ message }: { message: string | null | undefined }) {
  return message ? (
    <p role="alert" className="text-sm text-destructive">
      {message}
    </p>
  ) : null;
}

function PhoneStep({
  text,
  defaultPhone,
  notice,
  turnstile,
  onSent,
}: {
  text: SignInText;
  defaultPhone: string;
  notice: string | undefined;
  turnstile: { siteKey: string; nonce: string | undefined } | undefined;
  onSent: (phone: string, challenge: ChallengeIssued) => void;
}) {
  const id = useId();
  const [token, setToken] = useState<string | null>(null);
  // A Turnstile token works once: a new widget after each try gives the next one.
  const [widget, setWidget] = useState(0);
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    phone: z
      .string()
      .trim()
      .regex(/^[0-9+()\-\s]{10,20}$/u, text.phone.invalid),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { phone: defaultPhone },
  });
  const { errors, isSubmitting } = form.formState;
  const needsToken = turnstile !== undefined && token === null;

  async function send({ phone }: Values) {
    setFailure(null);
    try {
      onSent(
        phone,
        await requestCode(phone, turnstile === undefined ? NO_HUMAN_CHECK : (token ?? "")),
      );
    } catch (error) {
      setToken(null);
      setWidget((count) => count + 1);
      const onPhone =
        error instanceof ApiError && error.fieldErrors.some((field) => field.pointer === "/phone");
      if (onPhone) form.setError("phone", { message: text.phone.invalid });
      else setFailure(problemMessage(error, text.errors));
    }
  }

  return (
    <form
      noValidate
      className="space-y-5"
      onSubmit={(event) => {
        void form.handleSubmit(send)(event);
      }}
    >
      <FormFailure message={notice} />
      <div className="space-y-2">
        <label htmlFor={`${id}-phone`} className="block text-sm font-medium">
          {text.phone.label}
        </label>
        <Input
          id={`${id}-phone`}
          type="tel"
          inputMode="tel"
          autoComplete="tel-national"
          aria-invalid={errors.phone !== undefined}
          aria-describedby={`${id}-phone-hint${errors.phone ? ` ${id}-phone-error` : ""}`}
          {...form.register("phone")}
        />
        <p id={`${id}-phone-hint`} className="text-sm text-muted-foreground">
          {text.phone.hint}
        </p>
        <FieldError id={`${id}-phone-error`} message={errors.phone?.message} />
      </div>
      {turnstile === undefined ? null : (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">{text.phone.humanCheck}</p>
          <Turnstile
            key={widget}
            siteKey={turnstile.siteKey}
            action="otp_request"
            nonce={turnstile.nonce}
            onToken={setToken}
          />
        </div>
      )}
      <FormFailure message={failure} />
      <Button type="submit" size="lg" className="w-full" disabled={isSubmitting || needsToken}>
        {isSubmitting ? text.phone.sending : text.phone.submit}
      </Button>
    </form>
  );
}

function CodeStep({
  text,
  challenge,
  onSignedIn,
  onConsentNeeded,
  onRestart,
}: {
  text: SignInText;
  challenge: ChallengeIssued;
  onSignedIn: (me: Me) => void;
  onConsentNeeded: (code: string, notice: PrivacyNotice) => void;
  onRestart: (notice?: string) => void;
}) {
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  // A new code may be asked for once the API allows it; until then the link waits, without a
  // ticking countdown (CLAUDE.md rule 7).
  const [canResend, setCanResend] = useState(false);
  useEffect(() => {
    // Bounded: the API allows a new code 30 s later, and a phone's clock can be far off.
    const wait = Math.min(
      MAX_RESEND_WAIT_MS,
      Math.max(0, Date.parse(challenge.resendAfter) - Date.now()),
    );
    const timer = setTimeout(() => {
      setCanResend(true);
    }, wait);
    return () => {
      clearTimeout(timer);
    };
  }, [challenge.resendAfter]);
  const schema = z.object({
    code: z
      .string()
      .trim()
      .regex(/^[0-9]{6}$/u, text.code.invalid),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { code: "" } });
  const { errors, isSubmitting } = form.formState;

  async function check({ code }: Values) {
    setFailure(null);
    try {
      onSignedIn((await verifyCode(challenge.challengeId, code)).user);
    } catch (error) {
      if (error instanceof ApiError && error.code === "CONSENT_REQUIRED") {
        onConsentNeeded(code, await privacyNotice());
      } else if (error instanceof ApiError && ["OTP_EXPIRED", "OTP_LOCKED"].includes(error.code)) {
        onRestart(problemMessage(error, text.errors));
      } else {
        setFailure(problemMessage(error, text.errors));
      }
    }
  }

  return (
    <form
      noValidate
      className="space-y-5"
      onSubmit={(event) => {
        void form.handleSubmit(check)(event);
      }}
    >
      <div className="space-y-2">
        <label htmlFor={`${id}-code`} className="block text-sm font-medium">
          {text.code.label}
        </label>
        <Input
          id={`${id}-code`}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          aria-invalid={errors.code !== undefined}
          aria-describedby={errors.code ? `${id}-code-error` : undefined}
          {...form.register("code")}
        />
        <FieldError id={`${id}-code-error`} message={errors.code?.message} />
      </div>
      <FormFailure message={failure} />
      <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? text.code.checking : text.code.submit}
      </Button>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        {canResend ? (
          <Button
            type="button"
            variant="link"
            className="px-0"
            onClick={() => {
              onRestart();
            }}
          >
            {text.code.resend}
          </Button>
        ) : (
          <p className="text-muted-foreground">{text.code.resendLater}</p>
        )}
        <Button
          type="button"
          variant="link"
          className="px-0"
          onClick={() => {
            onRestart();
          }}
        >
          {text.code.otherNumber}
        </Button>
      </div>
    </form>
  );
}

function ConsentStep({
  text,
  notice,
  onAgree,
}: {
  text: SignInText;
  notice: PrivacyNotice;
  /** Resolves to a message to show when agreeing didn't work, or null. */
  onAgree: (consent: ConsentInput) => Promise<string | null>;
}) {
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    account: z.boolean().refine((agreed) => agreed, { message: text.consent.accountRequired }),
    marketing: z.boolean(),
  });
  type Values = z.infer<typeof schema>;
  // Nothing is ticked for anyone: each purpose counts only when chosen (CLAUDE.md rule 7).
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { account: false, marketing: false },
  });
  const { errors, isSubmitting } = form.formState;
  const offersMarketing = notice.purposes.some((purpose) => purpose.purpose === "marketing");

  async function agree(values: Values) {
    setFailure(null);
    setFailure(
      await onAgree({
        noticeVersion: notice.version,
        purposes: ["account", ...(values.marketing ? (["marketing"] as const) : [])],
      }),
    );
  }

  return (
    <form
      noValidate
      className="space-y-5"
      onSubmit={(event) => {
        void form.handleSubmit(agree)(event);
      }}
    >
      <p className="text-sm">
        <a
          href="/privacy"
          target="_blank"
          rel="noopener"
          className="font-medium text-primary underline underline-offset-4"
        >
          {text.consent.notice}
        </a>
      </p>
      <div className="space-y-2">
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 size-5 shrink-0 accent-primary"
            aria-invalid={errors.account !== undefined}
            aria-describedby={errors.account ? `${id}-account-error` : undefined}
            {...form.register("account")}
          />
          <span>{text.consent.account}</span>
        </label>
        <FieldError id={`${id}-account-error`} message={errors.account?.message} />
      </div>
      {offersMarketing ? (
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 size-5 shrink-0 accent-primary"
            {...form.register("marketing")}
          />
          <span>{text.consent.marketing}</span>
        </label>
      ) : null}
      <FormFailure message={failure} />
      <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
        {text.consent.submit}
      </Button>
    </form>
  );
}

function AuthenticatorStep({ text, onDone }: { text: SignInText; onDone: () => void }) {
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    code: z
      .string()
      .trim()
      .regex(/^[0-9]{6}$/u, text.authenticator.invalid),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { code: "" } });
  const { errors, isSubmitting } = form.formState;

  async function check({ code }: Values) {
    setFailure(null);
    try {
      await signInWithAuthenticator(code);
      onDone();
    } catch (error) {
      setFailure(problemMessage(error, text.errors));
    }
  }

  return (
    <form
      noValidate
      className="space-y-5"
      onSubmit={(event) => {
        void form.handleSubmit(check)(event);
      }}
    >
      <div className="space-y-2">
        <label htmlFor={`${id}-totp`} className="block text-sm font-medium">
          {text.authenticator.label}
        </label>
        <Input
          id={`${id}-totp`}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          aria-invalid={errors.code !== undefined}
          aria-describedby={errors.code ? `${id}-totp-error` : undefined}
          {...form.register("code")}
        />
        <FieldError id={`${id}-totp-error`} message={errors.code?.message} />
      </div>
      <FormFailure message={failure} />
      <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? text.authenticator.checking : text.authenticator.submit}
      </Button>
    </form>
  );
}
