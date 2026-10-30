import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/** Ops' blocks on beds from the browser (step 5.1, ADR 0044). */

export type BlockInput = Schemas["BlockInput"];
export type Block = Schemas["BlockInfo"];

export function placeBlock(bedId: string, body: BlockInput): Promise<Block> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/beds/{bed_id}/blocks", {
        params: { path: { bed_id: bedId } },
        body,
        headers,
      }),
    ),
  );
}

export function endBlock(blockId: string, on: string): Promise<Block> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/blocks/{block_id}/end", {
        params: { path: { block_id: blockId } },
        body: { on },
        headers,
      }),
    ),
  );
}
