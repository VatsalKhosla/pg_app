import type { Metadata, Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { SignOutButton } from "@/components/auth/sign-out-button";
import { buttonVariants } from "@/components/ui/button";
import { FIELD_VISITS_PATH, OPS_LISTINGS_PATH, STAFF_HOME_PATH } from "@/lib/auth/routes";
import { isOps, requireStaff } from "@/lib/auth/session";

const ROLES = ["field_agent", "ops", "admin"] as const;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Staff");
  return { title: t("homeMetaTitle"), robots: { index: false, follow: false } };
}

export default async function StaffHomePage() {
  const me = await requireStaff(STAFF_HOME_PATH);
  const t = await getTranslations("Staff");
  const tAccount = await getTranslations("Account");
  const roles = ROLES.filter((role) => me.roles.includes(role));
  // What each role opens: the ops console for ops and admins, the visits for field agents.
  const tools: { href: Route; label: string }[] = [];
  if (isOps(me)) tools.push({ href: OPS_LISTINGS_PATH, label: t("opsConsole") });
  if (me.roles.includes("field_agent")) {
    tools.push({ href: FIELD_VISITS_PATH, label: t("fieldVisits") });
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-8 px-4 py-10 sm:py-16">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("homeTitle")}</h1>
        <p className="text-muted-foreground">{t("signedInAs", { name: me.name ?? me.phone })}</p>
      </div>
      <section aria-labelledby="roles-title" className="space-y-2">
        <h2 id="roles-title" className="text-lg font-semibold">
          {t("roles")}
        </h2>
        <ul className="flex flex-wrap gap-2">
          {roles.map((role) => (
            <li key={role} className="rounded-full border px-3 py-1 text-sm">
              {t(`role.${role}`)}
            </li>
          ))}
        </ul>
      </section>
      <nav aria-label={t("tools")} className="flex flex-wrap gap-3">
        {tools.map((tool) => (
          <Link key={tool.href} href={tool.href} className={buttonVariants({ size: "lg" })}>
            {tool.label}
          </Link>
        ))}
      </nav>
      {tools.length === 0 ? <p className="text-muted-foreground">{t("comingSoon")}</p> : null}
      <div className="border-t pt-6">
        <SignOutButton
          label={tAccount("signOut")}
          busyLabel={tAccount("signingOut")}
          failedLabel={tAccount("signOutFailed")}
        />
      </div>
    </div>
  );
}
