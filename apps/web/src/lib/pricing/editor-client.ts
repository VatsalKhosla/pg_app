import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * The pricing editor's calls from the browser (step 4.6, ADR 0041). Every change to a draft
 * answers with the whole rule set as it now stands, its problems included; the page reads
 * through the server's client, and these are for the forms and the live preview.
 */

export type RuleSet = Schemas["RuleSetInfo"];
export type RuleInput = Schemas["PricingRuleInput"];
export type Preview = Schemas["PricingPreview"];

export function startDraft(propertyId: string): Promise<RuleSet> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/properties/{property_id}/rule-sets/draft", {
        params: { path: { property_id: propertyId } },
        headers,
      }),
    ),
  );
}

export function addRule(ruleSetId: string, body: RuleInput): Promise<RuleSet> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/rule-sets/{rule_set_id}/rules", {
        params: { path: { rule_set_id: ruleSetId } },
        body,
        headers,
      }),
    ),
  );
}

export function replaceRule(ruleId: string, body: RuleInput): Promise<RuleSet> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.PUT("/v1/ops/rules/{rule_id}", {
        params: { path: { rule_id: ruleId } },
        body,
        headers,
      }),
    ),
  );
}

export function removeRule(ruleId: string): Promise<RuleSet> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.DELETE("/v1/ops/rules/{rule_id}", {
        params: { path: { rule_id: ruleId } },
        headers,
      }),
    ),
  );
}

export function activateDraft(ruleSetId: string, note: string): Promise<RuleSet> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/rule-sets/{rule_set_id}/activate", {
        params: { path: { rule_set_id: ruleSetId } },
        body: { note },
        headers,
      }),
    ),
  );
}

export async function discardDraft(ruleSetId: string): Promise<void> {
  await withCsrf((headers) =>
    unwrap(
      browserApi.DELETE("/v1/ops/rule-sets/{rule_set_id}", {
        params: { path: { rule_set_id: ruleSetId } },
        headers,
      }),
    ),
  );
}

/** What a quote made today would say were the version in force; nothing is stored. */
export function previewPrice(
  ruleSetId: string,
  { room, moveIn, stay }: { room: string; moveIn: string; stay: number },
  signal?: AbortSignal,
): Promise<Preview> {
  return unwrap(
    browserApi.GET("/v1/ops/rule-sets/{rule_set_id}/preview", {
      params: { path: { rule_set_id: ruleSetId }, query: { room, moveIn, stay } },
      ...(signal === undefined ? {} : { signal }),
    }),
  );
}
