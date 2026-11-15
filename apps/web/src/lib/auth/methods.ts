import "server-only";

import type { Schemas } from "@pg-platform/api-client";

import { privacy } from "@/content/legal/en-IN/privacy";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";

export type SignInMethods = Schemas["SignInMethods"];

export interface SignInSetup {
  methods: SignInMethods;
  /** The privacy notice's version, which a Google sign-in's consent names. */
  noticeVersion: string;
}

/**
 * The ways to sign in here now (phone codes wait for the text sender's registration; ADR 0068),
 * and the notice consent names. If the API can't say, email codes alone (the form then reports
 * what's wrong when used), and the notice this site shows, which is the API's by design.
 */
export async function getSignInSetup(): Promise<SignInSetup> {
  try {
    const api = await getServerApi();
    const [methods, notice] = await Promise.all([
      unwrap(api.GET("/v1/auth/methods")),
      unwrap(api.GET("/v1/privacy-notice")),
    ]);
    return { methods, noticeVersion: notice.version };
  } catch {
    return {
      methods: { email: true, phone: false, google: false },
      noticeVersion: privacy.version,
    };
  }
}

/** The ways a code can go, email first; email alone if, oddly, neither is on. */
export function codeChannels(methods: SignInMethods): ("email" | "phone")[] {
  const channels: ("email" | "phone")[] = [];
  if (methods.email) channels.push("email");
  if (methods.phone) channels.push("phone");
  return channels.length === 0 ? ["email"] : channels;
}
