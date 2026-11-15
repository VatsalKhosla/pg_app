import "server-only";

import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";

import type {
  OpsPoliceVerification,
  OpsRentAgreement,
  OwnerPoliceVerification,
  RentAgreement,
  StudentPoliceVerification,
} from "./client";

/**
 * A booking's rent agreement and police verification, read on the server for the person viewing
 * (ADR 0070). A booking that was never confirmed has neither: null, as for anyone else's (the
 * page itself has already answered 404 for those).
 */
async function orNull<T>(call: Promise<T>): Promise<T | null> {
  try {
    return await call;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function studentAgreement(code: string): Promise<RentAgreement | null> {
  const api = await getServerApi();
  const path = { params: { path: { code } } };
  return orNull(unwrap(api.GET("/v1/bookings/{code}/agreement", path)));
}

export async function studentPoliceVerification(
  code: string,
): Promise<StudentPoliceVerification | null> {
  const api = await getServerApi();
  const path = { params: { path: { code } } };
  return orNull(unwrap(api.GET("/v1/bookings/{code}/police-verification", path)));
}

export async function ownerAgreement(code: string): Promise<RentAgreement | null> {
  const api = await getServerApi();
  const path = { params: { path: { code } } };
  return orNull(unwrap(api.GET("/v1/owner/bookings/{code}/agreement", path)));
}

export async function ownerPoliceVerification(
  code: string,
): Promise<OwnerPoliceVerification | null> {
  const api = await getServerApi();
  const path = { params: { path: { code } } };
  return orNull(unwrap(api.GET("/v1/owner/bookings/{code}/police-verification", path)));
}

export async function opsAgreement(code: string): Promise<OpsRentAgreement | null> {
  const api = await getServerApi();
  const path = { params: { path: { code } } };
  return orNull(unwrap(api.GET("/v1/ops/bookings/{code}/agreement", path)));
}

export async function opsPoliceVerification(code: string): Promise<OpsPoliceVerification | null> {
  const api = await getServerApi();
  const path = { params: { path: { code } } };
  return orNull(unwrap(api.GET("/v1/ops/bookings/{code}/police-verification", path)));
}
