import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Placeholder, TrustPage, TrustSection } from "@/components/trust/trust-page";
import { brand } from "@/config/brand";
import { company } from "@/config/company";
import { trustMetadata } from "@/lib/trust/metadata";
import { trustPages } from "@/lib/trust/pages";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("About");
  return trustMetadata("about", t("title", { brand: brand.name }), t("description"));
}

/** Who runs the site and why (step 3.8): the founders' names and faces are part of looking real
 * (PRODUCT_CONTEXT §5), and come only from them. */
export default async function AboutPage() {
  const t = await getTranslations("About");
  const tTrust = await getTranslations("Trust");
  return (
    <TrustPage title={t("title", { brand: brand.name })} intro={t("intro")}>
      <TrustSection id="why" title={t("whyTitle")}>
        <p className="leading-7">{t("why")}</p>
      </TrustSection>
      <TrustSection id="how" title={t("differentTitle")}>
        <ul className="list-disc space-y-2 pl-5 leading-7">
          <li>{t("verified")}</li>
          <li>{t("honest")}</li>
          <li>{t("free")}</li>
          <li>
            {t("token")}{" "}
            <Link
              href={trustPages.tokenProtection}
              className="font-medium text-primary underline underline-offset-4"
            >
              {tTrust("pages.tokenProtection")}
            </Link>
          </li>
        </ul>
      </TrustSection>
      <TrustSection id="team" title={t("teamTitle")}>
        {company.founders.length === 0 ? (
          <p>
            <Placeholder fact={tTrust("facts.founder")} />
          </p>
        ) : (
          <ul className="grid gap-6 sm:grid-cols-2">
            {company.founders.map((founder) => (
              <li key={founder.name} className="flex items-center gap-4">
                <Image
                  src={founder.photo}
                  alt=""
                  width={96}
                  height={96}
                  className="size-24 rounded-full object-cover"
                />
                <div>
                  <p className="font-semibold">{founder.name}</p>
                  <p className="text-sm text-muted-foreground">{founder.role}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="leading-7">
          {company.legalName === null ? (
            <Placeholder fact={tTrust("facts.legalName")} />
          ) : (
            t("registered", { brand: brand.name, legalName: company.legalName })
          )}
        </p>
      </TrustSection>
      <p>
        <Link
          href={trustPages.contact}
          className="font-medium text-primary underline underline-offset-4"
        >
          {t("contact")}
        </Link>
      </p>
    </TrustPage>
  );
}
