import path from "node:path";

/**
 * Where scripts/e2e-api.sh writes the API's JSON log (Playwright runs from apps/web). Outside
 * test-results, which Playwright empties when a run starts, after the API has opened the file.
 */
export const API_LOG = path.resolve(process.cwd(), ".e2e-api.log");
