import type { Schemas } from "@pg-platform/api-client";

import type { Scope } from "@/components/scope";
import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/** Blocks on beds from the browser: ops' (step 5.1, ADR 0044), and owners' own (step 7.2). */

export type BlockInput = Schemas["BlockInput"];
export type Block = Schemas["BlockInfo"];

export function placeBlock(bedId: string, body: BlockInput, scope: Scope = "ops"): Promise<Block> {
  const params = { path: { bed_id: bedId } };
  return withCsrf((headers) =>
    unwrap(
      scope === "owner"
        ? browserApi.POST("/v1/owner/beds/{bed_id}/blocks", { params, body, headers })
        : browserApi.POST("/v1/ops/beds/{bed_id}/blocks", { params, body, headers }),
    ),
  );
}

export function endBlock(blockId: string, on: string, scope: Scope = "ops"): Promise<Block> {
  const params = { path: { block_id: blockId } };
  const body = { on };
  return withCsrf((headers) =>
    unwrap(
      scope === "owner"
        ? browserApi.POST("/v1/owner/blocks/{block_id}/end", { params, body, headers })
        : browserApi.POST("/v1/ops/blocks/{block_id}/end", { params, body, headers }),
    ),
  );
}
