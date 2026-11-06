import type { Schemas } from "@pg-platform/api-client";

import type { Scope } from "@/components/scope";
import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * The pricing editor's calls from the browser (step 4.6, ADR 0041). Every change to a draft
 * answers with the whole rule set as it now stands, its problems included; the page reads
 * through the server's client, and these are for the forms and the live preview. Owners call
 * the same editor's routes for their own PGs (step 7.4, ADR 0063).
 */

export type RuleSet = Schemas["RuleSetInfo"];
export type RuleInput = Schemas["PricingRuleInput"];
export type Preview = Schemas["PricingPreview"];

export function startDraft(propertyId: string, scope: Scope = "ops"): Promise<RuleSet> {
  const params = { path: { property_id: propertyId } };
  return withCsrf((headers) =>
    unwrap(
      scope === "owner"
        ? browserApi.POST("/v1/owner/properties/{property_id}/rule-sets/draft", { params, headers })
        : browserApi.POST("/v1/ops/properties/{property_id}/rule-sets/draft", { params, headers }),
    ),
  );
}

export function addRule(
  ruleSetId: string,
  body: RuleInput,
  scope: Scope = "ops",
): Promise<RuleSet> {
  const params = { path: { rule_set_id: ruleSetId } };
  return withCsrf((headers) =>
    unwrap(
      scope === "owner"
        ? browserApi.POST("/v1/owner/rule-sets/{rule_set_id}/rules", { params, body, headers })
        : browserApi.POST("/v1/ops/rule-sets/{rule_set_id}/rules", { params, body, headers }),
    ),
  );
}

export function replaceRule(
  ruleId: string,
  body: RuleInput,
  scope: Scope = "ops",
): Promise<RuleSet> {
  const params = { path: { rule_id: ruleId } };
  return withCsrf((headers) =>
    unwrap(
      scope === "owner"
        ? browserApi.PUT("/v1/owner/rules/{rule_id}", { params, body, headers })
        : browserApi.PUT("/v1/ops/rules/{rule_id}", { params, body, headers }),
    ),
  );
}

export function removeRule(ruleId: string, scope: Scope = "ops"): Promise<RuleSet> {
  const params = { path: { rule_id: ruleId } };
  return withCsrf((headers) =>
    unwrap(
      scope === "owner"
        ? browserApi.DELETE("/v1/owner/rules/{rule_id}", { params, headers })
        : browserApi.DELETE("/v1/ops/rules/{rule_id}", { params, headers }),
    ),
  );
}

export function activateDraft(
  ruleSetId: string,
  note: string,
  scope: Scope = "ops",
): Promise<RuleSet> {
  const params = { path: { rule_set_id: ruleSetId } };
  const body = { note };
  return withCsrf((headers) =>
    unwrap(
      scope === "owner"
        ? browserApi.POST("/v1/owner/rule-sets/{rule_set_id}/activate", { params, body, headers })
        : browserApi.POST("/v1/ops/rule-sets/{rule_set_id}/activate", { params, body, headers }),
    ),
  );
}

export async function discardDraft(ruleSetId: string, scope: Scope = "ops"): Promise<void> {
  const params = { path: { rule_set_id: ruleSetId } };
  await withCsrf((headers) =>
    unwrap(
      scope === "owner"
        ? browserApi.DELETE("/v1/owner/rule-sets/{rule_set_id}", { params, headers })
        : browserApi.DELETE("/v1/ops/rule-sets/{rule_set_id}", { params, headers }),
    ),
  );
}

/** What a quote made today would say were the version in force; nothing is stored. */
export function previewPrice(
  ruleSetId: string,
  { room, moveIn, stay }: { room: string; moveIn: string; stay: number },
  signal?: AbortSignal,
  scope: Scope = "ops",
): Promise<Preview> {
  const params = { path: { rule_set_id: ruleSetId }, query: { room, moveIn, stay } };
  const aborting = signal === undefined ? {} : { signal };
  return unwrap(
    scope === "owner"
      ? browserApi.GET("/v1/owner/rule-sets/{rule_set_id}/preview", { params, ...aborting })
      : browserApi.GET("/v1/ops/rule-sets/{rule_set_id}/preview", { params, ...aborting }),
  );
}
