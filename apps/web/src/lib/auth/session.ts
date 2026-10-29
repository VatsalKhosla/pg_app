import "server-only";

import type { Schemas } from "@pg-platform/api-client";
import type { Route } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";

import {
  ACCOUNT_PATH,
  SESSION_COOKIE,
  SIGN_IN_PATH,
  STAFF_HOME_PATH,
  STAFF_SIGN_IN_PATH,
  signInUrl,
} from "./routes";

export type Me = Schemas["Me"];

const STAFF_ROLES: readonly string[] = ["field_agent", "ops", "admin"];

/**
 * The signed-in person, or null. One call to the API per page request, shared by everything that
 * asks (React's cache), and none at all without a session cookie. Throws when the API fails.
 */
export const getSession = cache(async (): Promise<Me | null> => {
  if (!(await cookies()).has(SESSION_COOKIE)) return null;
  const api = await getServerApi();
  try {
    return await unwrap(api.GET("/v1/me"));
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
});

/** For the header: the session if the API answers, else signed out (the page reports trouble). */
export async function getSessionForHeader(): Promise<Me | null> {
  try {
    return await getSession();
  } catch {
    return null;
  }
}

/** Staff roles come only with a staff session (the API drops them from phone sign-ins). */
export function isStaff(me: Me): boolean {
  return me.roles.some((role) => STAFF_ROLES.includes(role));
}

/** The signed-in person, or a redirect to sign in and come back to `here`. */
export async function requireSession(here: Route): Promise<Me> {
  const me = await getSession();
  if (me === null) redirect(signInUrl(SIGN_IN_PATH, here));
  return me;
}

/** Whether the person is an owner: ops added their business with this phone number. */
export function isOwner(me: Me): boolean {
  return me.roles.includes("owner");
}

/**
 * An owner, signed in by phone: the owner area's people. Anyone else signed in goes to their
 * account page (the API refuses them anyway).
 */
export async function requireOwner(here: Route): Promise<Me> {
  const me = await requireSession(here);
  if (!isOwner(me)) redirect(ACCOUNT_PATH);
  return me;
}

/** Whether the person may use the ops console (ops and admins). */
export function isOps(me: Me): boolean {
  return me.roles.some((role) => role === "ops" || role === "admin");
}

/** A staff member in a staff session, or a redirect to the staff sign-in page. */
export async function requireStaff(here: Route): Promise<Me> {
  const me = await getSession();
  if (me === null || !isStaff(me)) redirect(signInUrl(STAFF_SIGN_IN_PATH, here));
  return me;
}

/**
 * Ops or an admin in a staff session: the ops console's people. Other staff go to the staff home,
 * which shows what their roles allow (the API refuses them anyway).
 */
export async function requireOps(here: Route): Promise<Me> {
  const me = await requireStaff(here);
  if (!isOps(me)) redirect(STAFF_HOME_PATH);
  return me;
}

/** Whether the person may change policies and rent bands (admins only, ADR 0036). */
export function isAdmin(me: Me): boolean {
  return me.roles.includes("admin");
}

/** An admin in a staff session; other staff go to the staff home (the API refuses them anyway). */
export async function requireAdmin(here: Route): Promise<Me> {
  const me = await requireStaff(here);
  if (!isAdmin(me)) redirect(STAFF_HOME_PATH);
  return me;
}

/**
 * A field agent, or ops or an admin, in a staff session: the field screens' people. The API shows
 * an agent only the visits booked for them, and ops all of them.
 */
export async function requireFieldStaff(here: Route): Promise<Me> {
  const me = await requireStaff(here);
  const allowed: readonly string[] = ["field_agent", "ops", "admin"];
  if (!me.roles.some((role) => allowed.includes(role))) redirect(STAFF_HOME_PATH);
  return me;
}
