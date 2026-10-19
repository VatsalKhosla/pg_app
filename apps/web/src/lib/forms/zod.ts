import { z } from "zod";

// Zod compiles object validators with `new Function` when it can. The Content Security Policy
// forbids eval (src/lib/security/csp.ts), and even Zod's probe for it is reported as a violation,
// so it interprets instead: plenty fast for forms. Import z from here, never from "zod".
z.config({ jitless: true });

export { z };
