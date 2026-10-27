import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { type Block, parseAgreement, spans } from "@/lib/agreement/markdown";

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

describe("parseAgreement", () => {
  it("reads headings, paragraphs and lists", () => {
    const blocks = parseAgreement(
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
    expect(parseAgreement("- One\nThen text").map((block) => block.kind)).toEqual([
      "list",
      "paragraph",
    ]);
  });

  it("shows anything else exactly as written, markup included", () => {
    expect(texts(parseAgreement("A <b>tag</b> and **an unmatched star"))).toEqual([
      "A <b>tag</b> and **an unmatched star",
    ]);
    expect(texts(parseAgreement("#### Too deep\n\n1. Numbered"))).toEqual([
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
});

describe("every version of the agreement on file", () => {
  const versions = readdirSync(AGREEMENTS).filter((name) => name.endsWith(".md"));

  it.each(versions)("%s uses only the Markdown the owner area shows", (name) => {
    const blocks = parseAgreement(readFileSync(path.join(AGREEMENTS, name), "utf8"));

    expect(blocks[0]).toMatchObject({ kind: "heading", level: 1 });
    // Nothing left over from Markdown the parser doesn't know: no stars or hashes shown, and no
    // paragraph that is really a numbered list.
    for (const text of texts(blocks)) expect(text).not.toMatch(/\*\*|^#/u);
    for (const block of blocks) {
      if (block.kind === "paragraph") expect(block.content[0]?.text).not.toMatch(/^\d+\. /u);
    }
  });
});
