import createClient, { type Client, type ClientOptions } from "openapi-fetch";

import type { components, paths } from "./generated/schema";

export type { components, operations, paths } from "./generated/schema";
export type { ClientOptions, Middleware } from "openapi-fetch";

/** Every schema the API declares, by name: `Schemas["Health"]`. */
export type Schemas = components["schemas"];

/** A client whose paths, parameters, bodies and responses all come from the API's schema. */
export type ApiClient = Client<paths>;

export function createApiClient(options: ClientOptions): ApiClient {
  return createClient<paths>(options);
}
