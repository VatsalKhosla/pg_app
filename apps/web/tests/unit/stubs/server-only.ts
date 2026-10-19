// `server-only` throws unless the bundler resolves it for the server, as Next.js does. Vitest
// isn't a bundler, so tests of server modules get this empty module instead.
export {};
