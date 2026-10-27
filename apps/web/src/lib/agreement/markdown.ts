/**
 * The owner agreement's text (apps/api/src/app/modules/catalog/data/agreements), as blocks to
 * render: headings ("#" to "###"), paragraphs, "- " lists and **bold**. The text is ours, but it
 * still becomes React elements, never HTML; anything else in it shows exactly as written.
 */

export interface Span {
  text: string;
  strong: boolean;
}

export type Block =
  | { kind: "heading"; level: 1 | 2 | 3; content: Span[] }
  | { kind: "paragraph"; content: Span[] }
  | { kind: "list"; items: Span[][] };

const HEADING = /^(#{1,3})\s+(.+)$/u;
const LIST_ITEM = /^[-*]\s+(.+)$/u;

/** A line's **bold** runs; with an unmatched "**", the whole line is plain. */
export function spans(text: string): Span[] {
  const parts = text.split("**");
  if (parts.length % 2 === 0) return [{ text, strong: false }];
  return parts
    .map((part, index) => ({ text: part, strong: index % 2 === 1 }))
    .filter((span) => span.text !== "");
}

export function parseAgreement(markdown: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: Span[][] | null = null;

  function flush() {
    if (paragraph.length > 0) {
      blocks.push({ kind: "paragraph", content: spans(paragraph.join(" ")) });
      paragraph = [];
    }
    if (list !== null) {
      blocks.push({ kind: "list", items: list });
      list = null;
    }
  }

  for (const raw of markdown.split(/\r?\n/u)) {
    const line = raw.trim();
    const heading = HEADING.exec(line);
    const item = LIST_ITEM.exec(line);
    if (line === "") {
      flush();
    } else if (heading?.[1] !== undefined && heading[2] !== undefined) {
      flush();
      const level = heading[1].length as 1 | 2 | 3;
      blocks.push({ kind: "heading", level, content: spans(heading[2]) });
    } else if (item?.[1] !== undefined) {
      if (paragraph.length > 0) flush();
      list ??= [];
      list.push(spans(item[1]));
    } else {
      if (list !== null) flush();
      paragraph.push(line);
    }
  }
  flush();
  return blocks;
}
