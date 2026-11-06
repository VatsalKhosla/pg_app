import { getFormatter, getTranslations } from "next-intl/server";
import type * as React from "react";

import { MarkdownText } from "@/components/content/markdown-text";
import { Card } from "@/components/ui/card";
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
    <div className="mx-auto w-full max-w-3xl space-y-8 px-gutter py-10 sm:py-16">
      <header className="space-y-3 border-b border-border/80 pb-6">
        <h1 className="text-display font-semibold tracking-tight text-balance text-foreground">
          {title}
        </h1>
        {intro === undefined ? null : (
          <p className="text-body-lg text-pretty text-muted-foreground">{intro}</p>
        )}
      </header>
      <div className="space-y-6">{children}</div>
    </div>
  );
}

/** A fact the founders haven't given yet, shown as such rather than invented (CLAUDE.md). */
export async function Placeholder({ fact }: { fact: string }) {
  const t = await getTranslations("Trust");
  return (
    <span className="inline-flex items-center rounded-md border border-warning/30 bg-warning-soft px-2 py-0.5 text-sm font-medium text-warning">
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
    <Card asChild className="space-y-3 rounded-2xl border-border/80 bg-card p-6">
      <section aria-labelledby={id}>
        <h2 id={id} className="text-title-2 font-semibold tracking-tight text-foreground">
          {title}
        </h2>
        <div className="space-y-3 text-body text-foreground/90">{children}</div>
      </section>
    </Card>
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
          className="rounded-xl border border-warning/30 bg-warning-soft p-4 text-sm font-medium text-warning"
        >
          {t("draft")}
        </p>
      ) : null}
      <p className="text-sm font-medium text-muted-foreground">
        {t("version", {
          version: document.version,
          updated: format.dateTime(new Date(`${document.updated}T00:00:00+05:30`), {
            dateStyle: "long",
            timeZone: "Asia/Kolkata",
          }),
        })}
      </p>
      <Card className="rounded-2xl border-border/80 bg-card p-6">
        <MarkdownText text={fillBlanks(document.text, blanks)} />
      </Card>
    </div>
  );
}
