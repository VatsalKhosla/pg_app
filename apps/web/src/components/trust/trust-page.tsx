import { getFormatter, getTranslations } from "next-intl/server";
import type * as React from "react";

import { MarkdownText } from "@/components/content/markdown-text";
import { isDraft, type LegalDocument } from "@/content/legal";
import { fillBlanks } from "@/lib/content/markdown";

/** A trust page's frame: its heading, a line under it, then the page. */
export function TrustPage({
  title,
  intro,
  children,
}: {
  title: string;
  intro?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto w-full max-w-3xl space-y-8 px-4 py-10 sm:px-6 sm:py-16">
      <header className="space-y-3">
        <h1 className="text-3xl font-bold tracking-tight text-balance sm:text-4xl">{title}</h1>
        {intro === undefined ? null : (
          <p className="text-lg text-pretty text-muted-foreground">{intro}</p>
        )}
      </header>
      {children}
    </div>
  );
}

/** A fact the founders haven't given yet, shown as such rather than invented (CLAUDE.md). */
export async function Placeholder({ fact }: { fact: string }) {
  const t = await getTranslations("Trust");
  return (
    <span className="rounded-sm bg-amber-500/15 px-1 font-medium">
      {t("placeholder", { fact })}
    </span>
  );
}

/** A section of a trust page, with its own heading. */
export function TrustSection({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="space-y-3">
      <h2 id={id} className="text-xl font-semibold tracking-tight">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** A legal text: marked DRAFT until a lawyer has reviewed it, with its version and date. */
export async function LegalText({
  document,
  blanks,
}: {
  document: LegalDocument;
  blanks: Record<string, string>;
}) {
  const t = await getTranslations("Trust");
  const format = await getFormatter();
  return (
    <div className="space-y-6">
      {isDraft(document) ? (
        <p
          role="note"
          className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 text-sm font-medium"
        >
          {t("draft")}
        </p>
      ) : null}
      <p className="text-sm text-muted-foreground">
        {t("version", {
          version: document.version,
          updated: format.dateTime(new Date(`${document.updated}T00:00:00+05:30`), {
            dateStyle: "long",
            timeZone: "Asia/Kolkata",
          }),
        })}
      </p>
      <MarkdownText text={fillBlanks(document.text, blanks)} />
    </div>
  );
}
