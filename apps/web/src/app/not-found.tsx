import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { ErrorMessage } from "@/components/layout/error-message";
import { Button } from "@/components/ui/button";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("NotFound");
  return { title: t("title") };
}

export default async function NotFound() {
  const t = await getTranslations("NotFound");

  return (
    <ErrorMessage
      title={t("title")}
      body={t("body")}
      action={
        <Button asChild>
          <Link href="/">{t("home")}</Link>
        </Button>
      }
    />
  );
}
