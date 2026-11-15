"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Mail, Smartphone } from "lucide-react";
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
  requestEmailCode,
  signInWithAuthenticator,
  verifyCode,
} from "@/lib/auth/client";

import { problemMessage } from "./problem-message";
import { Turnstile } from "./turnstile";

export interface SignInText {
  email: {
    title: string;
    intro: string;
    label: string;
    invalid: string;
    humanCheck: string;
    submit: string;
    sending: string;
    /** Switches to a phone number, where codes by text are on. */
    usePhone: string;
  };
  phone: {
    title: string;
    intro: string;
    label: string;
    hint: string;
    invalid: string;
    humanCheck: string;
    submit: string;
    sending: string;
    useEmail: string;
  };
  google: {
    continue: string;
    /** The consent box's words around the link to the notice: before, link text, after. */
    newHere: readonly [string, string, string];
    consentNeeded: string;
    or: string;
  };
  code: {
    title: string;
    /** "{destination}" is filled in by the browser, which knows it. */
    introEmail: string;
    introPhone: string;
    /** Shown when the API hands back the code: a test site, where nothing is sent. */
    developmentCode: string;
    label: string;
    invalid: string;
    submit: string;
    checking: string;
    resend: string;
    resendLater: string;
    otherEmail: string;
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

/** Where a code goes: an email address, or a phone by text (while texts are on). */
export type Channel = "email" | "phone";

/** How to start a Google sign-in: the API's start address, and the notice consent names. */
export interface GoogleStart {
  href: string;
  noticeVersion: string;
}

type Step =
  | { name: "start"; channel: Channel; address: string; notice?: string | undefined }
  | { name: "code"; channel: Channel; address: string; challenge: ChallengeIssued }
  | {
      name: "consent";
      channel: Channel;
      address: string;
      challenge: ChallengeIssued;
      code: string;
      notice: PrivacyNotice;
    }
  | { name: "profile"; me: Me }
  | { name: "authenticator" };

/**
 * Signing in: with Google, or with a code sent to an email address (or, while texts are on, a
 * phone). Then consent if this makes a new account (the API says so), the profile for new people,
 * or the authenticator code for staff. Finishing loads `next` afresh, so every part of the page
 * sees the new session.
 */
export function SignInFlow({
  text,
  next,
  mode,
  channels,
  google,
  notice,
  consentNeeded = false,
  turnstile,
}: {
  text: SignInText;
  next: Route;
  /** "staff" asks for the authenticator code after the code. */
  mode: "people" | "staff";
  /** The ways a code can go, first the one offered first; never empty. */
  channels: readonly Channel[];
  /** Offered when Google sign-in is set up (people only: staff have their own button). */
  google?: GoogleStart | undefined;
  /** Why the person is back here, such as a Google sign-in that didn't work. */
  notice?: string | undefined;
  /** A first Google sign-in came back for consent: point at the box. */
  consentNeeded?: boolean;
  turnstile?: { siteKey: string; nonce: string | undefined } | undefined;
}) {
  const [step, setStep] = useState<Step>({
    name: "start",
    channel: channels[0] ?? "email",
    address: "",
    notice,
  });
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

  const current =
    step.name === "start"
      ? text[step.channel]
      : step.name === "code"
        ? {
            title: text.code.title,
            intro: (step.channel === "email" ? text.code.introEmail : text.code.introPhone).replace(
              "{destination}",
              step.address,
            ),
          }
        : text[step.name];
  const other = channels.find((channel) => step.name === "start" && channel !== step.channel);

  return (
    <section aria-labelledby="sign-in-step" className="space-y-6">
      {step.name === "start" && google !== undefined ? (
        <>
          <GoogleButton text={text} start={google} next={next} consentNeeded={consentNeeded} />
          <div className="flex items-center gap-3 text-xs font-medium text-muted-foreground uppercase">
            <span aria-hidden="true" className="h-px flex-1 bg-border" />
            {text.google.or}
            <span aria-hidden="true" className="h-px flex-1 bg-border" />
          </div>
        </>
      ) : null}
      <div className="space-y-1.5">
        <h2
          id="sign-in-step"
          ref={heading}
          tabIndex={-1}
          className="text-title-3 font-semibold tracking-tight text-foreground outline-none"
        >
          {current.title}
        </h2>
        <p className="text-body-sm text-muted-foreground">{current.intro}</p>
      </div>
      {step.name === "start" ? (
        <StartStep
          key={step.channel}
          text={text}
          channel={step.channel}
          defaultAddress={step.address}
          notice={step.notice}
          turnstile={turnstile}
          onSent={(address, challenge) => {
            setStep({ name: "code", channel: step.channel, address, challenge });
          }}
        />
      ) : null}
      {other === undefined ? null : (
        <Button
          type="button"
          variant="link"
          className="h-auto gap-2 px-0"
          onClick={() => {
            setStep({ name: "start", channel: other, address: "" });
          }}
        >
          {other === "phone" ? (
            <Smartphone aria-hidden="true" className="size-4" />
          ) : (
            <Mail aria-hidden="true" className="size-4" />
          )}
          {other === "phone" ? text.email.usePhone : text.phone.useEmail}
        </Button>
      )}
      {step.name === "code" ? (
        <CodeStep
          text={text}
          channel={step.channel}
          challenge={step.challenge}
          onSignedIn={signedIn}
          onConsentNeeded={(code, notice) => {
            setStep({ ...step, name: "consent", code, notice });
          }}
          onRestart={(notice) => {
            setStep({ name: "start", channel: step.channel, address: step.address, notice });
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
                setStep({
                  name: "start",
                  channel: step.channel,
                  address: step.address,
                  notice: text.errors.OTP_EXPIRED,
                });
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
    <p id={id} className="text-sm font-medium text-destructive">
      {message}
    </p>
  ) : null;
}

function FormFailure({ message }: { message: string | null | undefined }) {
  return message ? (
    <p
      role="alert"
      className="rounded-xl border border-destructive/25 bg-destructive-soft px-3.5 py-2.5 text-sm font-medium text-destructive"
    >
      {message}
    </p>
  ) : null;
}

/** Loose on purpose: the API says exactly which addresses it takes. */
const LOOKS_LIKE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/u;
const LOOKS_LIKE_PHONE = /^[0-9+()\-\s]{10,20}$/u;

/** The address (an email address or a phone number) to send a code to. */
function StartStep({
  text,
  channel,
  defaultAddress,
  notice,
  turnstile,
  onSent,
}: {
  text: SignInText;
  channel: Channel;
  defaultAddress: string;
  notice: string | undefined;
  turnstile: { siteKey: string; nonce: string | undefined } | undefined;
  onSent: (address: string, challenge: ChallengeIssued) => void;
}) {
  const id = useId();
  const [token, setToken] = useState<string | null>(null);
  // A Turnstile token works once: a new widget after each try gives the next one.
  const [widget, setWidget] = useState(0);
  const [failure, setFailure] = useState<string | null>(null);
  const words = text[channel];
  const schema = z.object({
    address: z
      .string()
      .trim()
      .regex(channel === "email" ? LOOKS_LIKE_EMAIL : LOOKS_LIKE_PHONE, words.invalid),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { address: defaultAddress },
  });
  const { errors, isSubmitting } = form.formState;
  const needsToken = turnstile !== undefined && token === null;

  async function send({ address }: Values) {
    setFailure(null);
    const humanCheck = turnstile === undefined ? NO_HUMAN_CHECK : (token ?? "");
    try {
      onSent(
        address,
        channel === "email"
          ? await requestEmailCode(address, humanCheck)
          : await requestCode(address, humanCheck),
      );
    } catch (error) {
      setToken(null);
      setWidget((count) => count + 1);
      const onField =
        error instanceof ApiError &&
        error.fieldErrors.some((field) => field.pointer === `/${channel}`);
      if (onField) form.setError("address", { message: words.invalid });
      else setFailure(problemMessage(error, text.errors));
    }
  }

  return (
    <form
      method="post"
      noValidate
      className="space-y-5"
      onSubmit={(event) => {
        void form.handleSubmit(send)(event);
      }}
    >
      <FormFailure message={notice} />
      <div className="space-y-2">
        <label htmlFor={`${id}-address`} className="block text-sm font-medium text-foreground">
          {words.label}
        </label>
        {channel === "email" ? (
          <Input
            id={`${id}-address`}
            type="email"
            inputMode="email"
            autoComplete="email"
            spellCheck={false}
            aria-invalid={errors.address !== undefined}
            aria-describedby={errors.address ? `${id}-address-error` : undefined}
            {...form.register("address")}
          />
        ) : (
          <>
            <Input
              id={`${id}-address`}
              type="tel"
              inputMode="tel"
              autoComplete="tel-national"
              aria-invalid={errors.address !== undefined}
              aria-describedby={`${id}-address-hint${errors.address ? ` ${id}-address-error` : ""}`}
              {...form.register("address")}
            />
            <p id={`${id}-address-hint`} className="text-sm text-muted-foreground">
              {text.phone.hint}
            </p>
          </>
        )}
        <FieldError id={`${id}-address-error`} message={errors.address?.message} />
      </div>
      {turnstile === undefined ? null : (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">{words.humanCheck}</p>
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
      <Button
        type="submit"
        size="lg"
        shape="pill"
        className="w-full"
        disabled={isSubmitting || needsToken}
      >
        {isSubmitting ? words.sending : words.submit}
      </Button>
    </form>
  );
}

/**
 * Off to Google, by a link (a form's redirect to Google would break the site's form-action
 * rule). A first sign-in makes the account, which needs consent: the box, never ticked for anyone,
 * adds it to the link (CLAUDE.md rule 7). Someone with an account needn't tick it.
 */
function GoogleButton({
  text,
  start,
  next,
  consentNeeded,
}: {
  text: SignInText;
  start: GoogleStart;
  next: Route;
  consentNeeded: boolean;
}) {
  const id = useId();
  const [agreed, setAgreed] = useState(false);
  const query = new URLSearchParams({ next });
  if (agreed) {
    query.set("notice", start.noticeVersion);
    query.set("purpose", "account");
  }
  const [before, link, after] = text.google.newHere;

  return (
    <div className="space-y-3">
      <a
        href={`${start.href}?${query.toString()}`}
        className="flex min-h-12 w-full items-center justify-center gap-3 rounded-full border border-border bg-card px-5 text-base font-semibold text-foreground shadow-xs transition-[background-color,box-shadow] duration-(--duration-fast) outline-none hover:bg-accent hover:shadow-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-reduce:transition-none"
      >
        <GoogleMark />
        {text.google.continue}
      </a>
      <label
        htmlFor={`${id}-agree`}
        className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 text-sm transition-colors has-[:checked]:border-primary has-[:checked]:bg-primary-soft/50 ${consentNeeded && !agreed ? "border-marigold-border bg-marigold-soft" : "border-border/70 bg-surface/40"}`}
      >
        <input
          id={`${id}-agree`}
          type="checkbox"
          checked={agreed}
          onChange={(event) => {
            setAgreed(event.target.checked);
          }}
          aria-describedby={consentNeeded ? `${id}-agree-needed` : undefined}
          className="mt-0.5 size-5 shrink-0 accent-primary"
        />
        <span className="leading-snug text-foreground">
          {before}
          <a
            href="/privacy"
            target="_blank"
            rel="noopener"
            className="font-semibold text-primary underline underline-offset-4"
          >
            {link}
          </a>
          {after}
        </span>
      </label>
      {consentNeeded ? (
        <p id={`${id}-agree-needed`} className="text-sm font-medium text-marigold-soft-foreground">
          {text.google.consentNeeded}
        </p>
      ) : null}
    </div>
  );
}

/** Google's "G", in its own colours, as Google's sign-in branding asks. */
function GoogleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 48 48" className="size-5 shrink-0">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}

function CodeStep({
  text,
  channel,
  challenge,
  onSignedIn,
  onConsentNeeded,
  onRestart,
}: {
  text: SignInText;
  channel: Channel;
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
      method="post"
      noValidate
      className="space-y-5"
      onSubmit={(event) => {
        void form.handleSubmit(check)(event);
      }}
    >
      {challenge.developmentCode ? (
        <p className="rounded-xl border border-dashed border-primary/40 bg-primary-soft/60 px-3.5 py-2.5 font-mono text-sm font-medium text-foreground">
          {text.code.developmentCode.replace("{code}", challenge.developmentCode)}
        </p>
      ) : null}
      <div className="space-y-2">
        <label htmlFor={`${id}-code`} className="block text-sm font-medium text-foreground">
          {text.code.label}
        </label>
        <Input
          id={`${id}-code`}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          className="font-mono tracking-widest"
          aria-invalid={errors.code !== undefined}
          aria-describedby={errors.code ? `${id}-code-error` : undefined}
          {...form.register("code")}
        />
        <FieldError id={`${id}-code-error`} message={errors.code?.message} />
      </div>
      <FormFailure message={failure} />
      <Button type="submit" size="lg" shape="pill" className="w-full" disabled={isSubmitting}>
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
          {channel === "email" ? text.code.otherEmail : text.code.otherNumber}
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
      method="post"
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
          className="font-semibold text-primary underline underline-offset-4 hover:text-primary-hover"
        >
          {text.consent.notice}
        </a>
      </p>
      <div className="space-y-2">
        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-surface/50 p-3.5 text-sm transition-colors hover:bg-accent/50 has-[:checked]:border-primary has-[:checked]:bg-primary-soft/50">
          <input
            type="checkbox"
            className="mt-0.5 size-5 shrink-0 accent-primary"
            aria-invalid={errors.account !== undefined}
            aria-describedby={errors.account ? `${id}-account-error` : undefined}
            {...form.register("account")}
          />
          <span className="leading-snug text-foreground">{text.consent.account}</span>
        </label>
        <FieldError id={`${id}-account-error`} message={errors.account?.message} />
      </div>
      {offersMarketing ? (
        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-surface/50 p-3.5 text-sm transition-colors hover:bg-accent/50 has-[:checked]:border-primary has-[:checked]:bg-primary-soft/50">
          <input
            type="checkbox"
            className="mt-0.5 size-5 shrink-0 accent-primary"
            {...form.register("marketing")}
          />
          <span className="leading-snug text-foreground">{text.consent.marketing}</span>
        </label>
      ) : null}
      <FormFailure message={failure} />
      <Button type="submit" size="lg" shape="pill" className="w-full" disabled={isSubmitting}>
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
      method="post"
      noValidate
      className="space-y-5"
      onSubmit={(event) => {
        void form.handleSubmit(check)(event);
      }}
    >
      <div className="space-y-2">
        <label htmlFor={`${id}-totp`} className="block text-sm font-medium text-foreground">
          {text.authenticator.label}
        </label>
        <Input
          id={`${id}-totp`}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          className="font-mono tracking-widest"
          aria-invalid={errors.code !== undefined}
          aria-describedby={errors.code ? `${id}-totp-error` : undefined}
          {...form.register("code")}
        />
        <FieldError id={`${id}-totp-error`} message={errors.code?.message} />
      </div>
      <FormFailure message={failure} />
      <Button type="submit" size="lg" shape="pill" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? text.authenticator.checking : text.authenticator.submit}
      </Button>
    </form>
  );
}
