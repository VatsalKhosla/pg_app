"use client";

import { createContext, type ReactNode, useContext } from "react";

/**
 * Whom an editor serves: ops, for any PG, or an owner, for their own (Phase 7, ADR 0063). The
 * same bed calendar and pricing editor call the API's ops or owner routes as this says; with no
 * provider, ops'.
 */
export type Scope = "ops" | "owner";

const ScopeContext = createContext<Scope>("ops");

export function ScopeProvider({ scope, children }: { scope: Scope; children: ReactNode }) {
  return <ScopeContext.Provider value={scope}>{children}</ScopeContext.Provider>;
}

export function useScope(): Scope {
  return useContext(ScopeContext);
}
