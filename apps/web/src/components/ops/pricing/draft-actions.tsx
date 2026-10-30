"use client";

import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { Field, FormOutcome } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { activateDraft, discardDraft, startDraft } from "@/lib/pricing/editor-client";

import { useOpsProblem } from "../problems";

const NOTE_MAX = 500;

/** The page for a version: the editor, showing `ruleSetId`. */
function versionPath(pricingPath: string, ruleSetId?: string): Route {
  return (ruleSetId === undefined ? pricingPath : `${pricingPath}?version=${ruleSetId}`) as Route;
}

/** Starts the PG's draft, a copy of its version in force, and shows it. */
export function StartDraft({
  propertyId,
  pricingPath,
}: {
  propertyId: string;
  pricingPath: string;
}) {
  const t = useTranslations("Ops.pricing");
  const problem = useOpsProblem();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setFailure(null);
    try {
      const draft = await startDraft(propertyId);
      startTransition(() => {
        router.push(versionPath(pricingPath, draft.id));
        router.refresh();
      });
    } catch (error) {
      setFailure(problem(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <Button
        type="button"
        disabled={busy || pending}
        onClick={() => {
          void start();
        }}
      >
        {busy || pending ? t("versions.starting") : t("versions.start")}
      </Button>
      <p className="text-sm text-muted-foreground">{t("versions.startHint")}</p>
      <FormOutcome failure={failure} />
    </div>
  );
}

/** A confirmation step in the page, its heading focused as it opens. */
function Confirmation({ title, children }: { title: string; children: React.ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null);
  const id = useId();
  useEffect(() => {
    heading.current?.focus();
  }, []);
  return (
    <section aria-labelledby={id} className="space-y-4 rounded-lg border border-primary/40 p-4">
      <h3 id={id} ref={heading} tabIndex={-1} className="font-semibold outline-none">
        {title}
      </h3>
      {children}
    </section>
  );
}

/**
 * Puts the draft in force from now, once ops confirm: new quotes and the PG's page use it, and
 * quotes and bookings already made keep their prices (rule 5). Audited by the API.
 */
export function ActivateDraft({
  ruleSetId,
  version,
  current,
  blocked,
  pricingPath,
}: {
  ruleSetId: string;
  version: number;
  /** The version in force now, which this one replaces; null for the PG's first. */
  current: number | null;
  blocked: boolean;
  pricingPath: string;
}) {
  const t = useTranslations("Ops.pricing");
  const problem = useOpsProblem();
  const router = useRouter();
  const [, startTransition] = useTransition();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function activate() {
    setBusy(true);
    setFailure(null);
    try {
      const active = await activateDraft(ruleSetId, note.trim());
      setOpen(false);
      startTransition(() => {
        router.replace(versionPath(pricingPath, active.id));
        router.refresh();
      });
    } catch (error) {
      setFailure(problem(error));
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="space-y-2">
        <Button
          type="button"
          disabled={blocked}
          aria-describedby={blocked ? `${id}-blocked` : undefined}
          onClick={() => {
            setOpen(true);
          }}
        >
          {t("activate.open")}
        </Button>
        {blocked ? (
          <p id={`${id}-blocked`} className="text-sm text-muted-foreground">
            {t("activate.blocked")}
          </p>
        ) : null}
      </div>
    );
  }
  return (
    <Confirmation title={t("activate.title", { version })}>
      <p>{current === null ? t("activate.first") : t("activate.replaces", { current })}</p>
      <Field id={`${id}-note`} label={t("activate.note")}>
        {(control) => (
          <Input
            {...control}
            maxLength={NOTE_MAX}
            value={note}
            onChange={(event) => {
              setNote(event.currentTarget.value);
            }}
          />
        )}
      </Field>
      <FormOutcome failure={failure} />
      <div className="flex flex-wrap gap-3">
        <Button
          type="button"
          disabled={busy}
          onClick={() => {
            void activate();
          }}
        >
          {busy ? t("activate.confirming") : t("activate.confirm")}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setOpen(false);
          }}
        >
          {t("activate.cancel")}
        </Button>
      </div>
    </Confirmation>
  );
}

/** Discards the draft and its rules, once ops confirm; the version in force stays as it is. */
export function DiscardDraft({
  ruleSetId,
  version,
  pricingPath,
}: {
  ruleSetId: string;
  version: number;
  pricingPath: string;
}) {
  const t = useTranslations("Ops.pricing");
  const problem = useOpsProblem();
  const router = useRouter();
  const [, startTransition] = useTransition();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function discard() {
    setBusy(true);
    setFailure(null);
    try {
      await discardDraft(ruleSetId);
      startTransition(() => {
        router.replace(versionPath(pricingPath));
        router.refresh();
      });
    } catch (error) {
      setFailure(problem(error));
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          setOpen(true);
        }}
      >
        {t("discard.open")}
      </Button>
    );
  }
  return (
    <Confirmation title={t("discard.title", { version })}>
      <p>{t("discard.explain")}</p>
      <FormOutcome failure={failure} />
      <div className="flex flex-wrap gap-3">
        <Button
          type="button"
          variant="destructive"
          disabled={busy}
          onClick={() => {
            void discard();
          }}
        >
          {busy ? t("discard.confirming") : t("discard.confirm")}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setOpen(false);
          }}
        >
          {t("discard.cancel")}
        </Button>
      </div>
    </Confirmation>
  );
}
