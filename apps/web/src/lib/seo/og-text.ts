import { createTranslator } from "next-intl";

import { defaultLocale } from "@/i18n/config";

import messages from "../../../messages/en-IN.json";

/**
 * The words on link pictures (opengraph-image). Next.js reads those modules outside the request
 * that next-intl's getTranslations needs (to work out their alt text, among others), so they
 * translate with the message file directly, as the global error page does.
 */
export const ogText = {
  pg: createTranslator({ locale: defaultLocale, messages, namespace: "Pg" }),
  landing: createTranslator({ locale: defaultLocale, messages, namespace: "Landing" }),
  brand: createTranslator({ locale: defaultLocale, messages, namespace: "Brand" }),
};
