import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { legalDocuments } from "@/content/legal";
import { type Block, blanksIn, fillBlanks, parseMarkdown, spans } from "@/lib/content/markdown";

// The agreement's versions, as the API serves them (ADR 0025).
const AGREEMENTS = path.resolve(process.cwd(), "../api/src/app/modules/catalog/data/agreements");

/** Every piece of text in the blocks, as it will show. */
function texts(blocks: Block[]): string[] {
  return blocks.flatMap((block) =>
    block.kind === "list"
      ? block.items.flatMap((item) => item.map((span) => span.text))
      : block.content.map((span) => span.text),
  );
}

describe("parseMarkdown", () => {
  it("reads headings, paragraphs and lists", () => {
    const blocks = parseMarkdown(
      "# The agreement\n\nOne paragraph\nover two lines.\n\n## 1. Fees\n\n- One fee\n- **Only** once\n\nAfter the list.\n",
    );

    expect(blocks).toEqual([
      { kind: "heading", level: 1, content: [{ text: "The agreement", strong: false }] },
      {
        kind: "paragraph",
        content: [{ text: "One paragraph over two lines.", strong: false }],
      },
      { kind: "heading", level: 2, content: [{ text: "1. Fees", strong: false }] },
      {
        kind: "list",
        items: [
          [{ text: "One fee", strong: false }],
          [
            { text: "Only", strong: true },
            { text: " once", strong: false },
          ],
        ],
      },
      { kind: "paragraph", content: [{ text: "After the list.", strong: false }] },
    ]);
  });

  it("ends a list where a paragraph starts without a blank line", () => {
    expect(parseMarkdown("- One\nThen text").map((block) => block.kind)).toEqual([
      "list",
      "paragraph",
    ]);
  });

  it("shows anything else exactly as written, markup included", () => {
    expect(texts(parseMarkdown("A <b>tag</b> and **an unmatched star"))).toEqual([
      "A <b>tag</b> and **an unmatched star",
    ]);
    expect(texts(parseMarkdown("#### Too deep\n\n1. Numbered"))).toEqual([
      "#### Too deep",
      "1. Numbered",
    ]);
  });
});

describe("spans", () => {
  it("marks the bold runs", () => {
    expect(spans("**DRAFT** for discussion")).toEqual([
      { text: "DRAFT", strong: true },
      { text: " for discussion", strong: false },
    ]);
  });

  it("links to this site's own pages, and shows any other link as written", () => {
    expect(spans("See our [grievances page](/grievances), **today**.")).toEqual([
      { text: "See our ", strong: false },
      { text: "grievances page", strong: false, href: "/grievances" },
      { text: ", ", strong: false },
      { text: "today", strong: true },
      { text: ".", strong: false },
    ]);
    for (const text of [
      "[elsewhere](https://example.com)",
      "[another site](//example.com)",
      "[a script](javascript:alert(1))",
    ]) {
      expect(spans(text)).toEqual([{ text, strong: false }]);
    }
  });
});

describe("blanks", () => {
  it("fills the ones it has values for and leaves the rest as written", () => {
    expect(fillBlanks("{brand} by {legalName}, {unknown}", { brand: "B", legalName: "L" })).toBe(
      "B by L, {unknown}",
    );
    expect(blanksIn("{a} and {b} and {a}")).toEqual(new Set(["a", "b"]));
  });
});

describe("every legal text", () => {
  // What the legal pages fill in (src/lib/content/legal.ts).
  const KNOWN = new Set([
    "brand",
    "legalName",
    "address",
    "supportEmail",
    "token",
    "freeCancelDays",
    "lateCancel",
    "confirmHours",
    "checkHours",
  ]);

  it.each(Object.entries(legalDocuments))("%s uses only known blanks and Markdown", (_, doc) => {
    expect([...blanksIn(doc.text)].filter((blank) => !KNOWN.has(blank))).toEqual([]);
    const blocks = parseMarkdown(doc.text);
    for (const text of texts(blocks)) expect(text).not.toMatch(/\*\*|^#|\]\(/u);
    expect(doc.version).toMatch(/^draft-\d+$|^\d{4}-\d{2}$/u);
  });
});

describe("every version of the agreement on file", () => {
  const versions = readdirSync(AGREEMENTS).filter((name) => name.endsWith(".md"));

  it.each(versions)("%s uses only the Markdown the owner area shows", (name) => {
    const blocks = parseMarkdown(readFileSync(path.join(AGREEMENTS, name), "utf8"));

    expect(blocks[0]).toMatchObject({ kind: "heading", level: 1 });
    // Nothing left over from Markdown the parser doesn't know: no stars or hashes shown, and no
    // paragraph that is really a numbered list.
    for (const text of texts(blocks)) expect(text).not.toMatch(/\*\*|^#/u);
    for (const block of blocks) {
      if (block.kind === "paragraph") expect(block.content[0]?.text).not.toMatch(/^\d+\. /u);
    }
  });
});
