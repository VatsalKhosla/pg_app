// The import brings next-intl's types into the program, which the augmentation below needs.
import "next-intl";

import type messages from "../../messages/en-IN.json";
import type { Locale } from "./config";

// Typed translations: an unknown message key or a missing argument fails the typecheck.
declare module "next-intl" {
  interface AppConfig {
    Locale: Locale;
    Messages: typeof messages;
  }
}
