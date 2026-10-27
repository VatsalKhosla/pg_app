import "server-only";

import type { Schemas } from "@pg-platform/api-client";

import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";

/**
 * The owner area's reads, for the signed-in owner (ADR 0025). Each is null for an owner whose
 * business ops haven't added yet: the API answers 404 until they do.
 */

async function orNull<T>(read: () => Promise<T>): Promise<T | null> {
  try {
    return await read();
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function getOwnProfile(): Promise<Schemas["OwnerInfo"] | null> {
  const api = await getServerApi();
  return orNull(() => unwrap(api.GET("/v1/owner/profile")));
}

export async function getAgreement(): Promise<Schemas["AgreementInfo"] | null> {
  const api = await getServerApi();
  return orNull(() => unwrap(api.GET("/v1/owner/agreement")));
}
