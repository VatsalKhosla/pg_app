# Owner agreement

Use this to publish a new version of the owner agreement, and to answer an owner who disputes what they agreed to. The design is in [ADR 0025](../adr/0025-owner-agreement.md).

Each version is one Markdown file in `apps/api/src/app/modules/catalog/data/agreements/`, named after the version (`draft-1.md`). `OWNER_AGREEMENT_VERSION` says which one owners accept now.

## Publish a new version

1. **Never edit a published file.** Owners may have accepted its text, and their acceptance names its SHA-256. A change is always a new file.
2. **Write the new file**, such as `2027-01.md`, starting with a `#` heading.
   - Use only headings (`#` to `###`), paragraphs, `- ` lists and `**bold**`: the owner area shows nothing else as formatting, and a web unit test fails on anything more.
   - Write `{brand}` where the brand name goes.
   - A version named `draft…` can't be used in production. The final text needs the founders' and a lawyer's review (CLAUDE.md).
3. **Review it in a pull request**, then merge and deploy it with `OWNER_AGREEMENT_VERSION` still naming the old version.
4. **Switch:** set `OWNER_AGREEMENT_VERSION` to the new version and redeploy the API. It won't start if the file is missing.
5. **Check:** every owner's page in the ops console (Owners) now shows that they accepted an older version, and an owner signing in is sent to the new text. They can't use the owner area until they accept it.

To roll back, set `OWNER_AGREEMENT_VERSION` to the old version again. Owners who accepted the new one are asked again for the old one, and every acceptance stays on record.

## An owner disputes what they agreed to

1. **Open the owner's page** in the ops console (Owners → the business). Each acceptance shows the version, the time (IST), the IP address, the browser, and the SHA-256 of the text.
2. **Find the exact text** in git: `git log --follow -- apps/api/src/app/modules/catalog/data/agreements/<version>.md`. The file's content, with `{brand}` replaced by the brand name, hashes to the SHA-256 shown.
3. **The audit log** has the same acceptance (`catalog.owner_agreement_accepted`) with the version and hash, and the owner as its actor.

Acceptances can't be changed or deleted: the database refuses. Don't try to work around that; ask the founders first.
