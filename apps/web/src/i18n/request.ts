import { getRequestConfig } from "next-intl/server";

import { defaultLocale, type Locale, timeZone } from "./config";

// One loader per locale, so each locale's messages are a separate chunk.
const messageLoaders = {
  "en-IN": () => import("../../messages/en-IN.json"),
} satisfies Record<Locale, () => Promise<unknown>>;

// Every request uses the default locale until a second one exists (see ./config.ts).
export default getRequestConfig(async () => {
  const locale = defaultLocale;
  const { default: messages } = await messageLoaders[locale]();
  return { locale, messages, timeZone };
});
