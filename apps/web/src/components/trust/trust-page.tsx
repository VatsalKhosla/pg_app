import { getFormatter, getTranslations } from "next-intl/server";
import type * as React from "react";

import { ArchWatermark } from "@/components/brand/editorial-art";
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
      <header className="relative space-y-3 overflow-hidden rounded-3xl border border-marigold-border bg-surface-warm p-6 shadow-xs sm:p-8">
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-1.5"
          style={{
            backgroundImage:
              "linear-gradient(90deg, var(--primary) 0%, var(--neem) 35%, var(--marigold) 70%, var(--ember) 100%)",
          }}
        />
        <ArchWatermark tone="marigold" className="absolute -right-6 -bottom-6 size-40 opacity-15" />
        <h1 className="relative text-display font-bold tracking-tight text-balance text-foreground">
          {title}
        </h1>
        {intro === undefined ? null : (
          <p className="relative text-body-lg text-pretty text-muted-foreground">{intro}</p>
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
    <span className="inline-flex items-center rounded-md border border-marigold-border bg-marigold-soft px-2 py-0.5 text-sm font-medium text-marigold-soft-foreground">
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
    <Card
      asChild
      className="relative space-y-3 overflow-hidden rounded-3xl border-border/80 bg-card p-6 sm:p-8"
    >
      <section aria-labelledby={id}>
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-1"
          style={{
            backgroundImage:
              "linear-gradient(90deg, var(--primary) 0%, var(--marigold) 50%, var(--ember) 100%)",
          }}
        />
        <h2 id={id} className="text-title-2 font-bold tracking-tight text-foreground">
          {title}
        </h2>
        <div className="space-y-3 text-body text-foreground">{children}</div>
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
