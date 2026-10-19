import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { SignOutButton } from "@/components/auth/sign-out-button";
import { STAFF_HOME_PATH } from "@/lib/auth/routes";
import { requireStaff } from "@/lib/auth/session";

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
      <p className="text-muted-foreground">{t("comingSoon")}</p>
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
