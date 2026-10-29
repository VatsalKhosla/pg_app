/**
 * Long texts written in Markdown, as blocks to render: the owner agreement
 * (apps/api/src/app/modules/catalog/data/agreements) and the legal pages (src/content/legal).
 * Headings ("#" to "###"), paragraphs, "- " lists, **bold** and links to this site's own pages,
 * [like this](/grievances). The texts are ours, but they still become React elements, never
 * HTML; anything else in them, a link elsewhere included, shows exactly as written.
 */

export interface Span {
  text: string;
  strong: boolean;
  /** A path on this site, for a link. */
  href?: string;
}

export type Block =
  | { kind: "heading"; level: 1 | 2 | 3; content: Span[] }
  | { kind: "paragraph"; content: Span[] }
  | { kind: "list"; items: Span[][] };

const HEADING = /^(#{1,3})\s+(.+)$/u;
const LIST_ITEM = /^[-*]\s+(.+)$/u;
// A link to a path on this site: "/" then anything but a second "/", a space or ")".
const LINK = /\[([^\]]+)\]\((\/(?!\/)[^\s)]*)\)/gu;

/** A run of text's **bold** parts; with an unmatched "**", the whole run is plain. */
function boldSpans(text: string): Span[] {
  const parts = text.split("**");
  if (parts.length % 2 === 0) return [{ text, strong: false }];
  return parts
    .map((part, index) => ({ text: part, strong: index % 2 === 1 }))
    .filter((span) => span.text !== "");
}

/** A line's links and **bold** runs. */
export function spans(text: string): Span[] {
  const found: Span[] = [];
  let from = 0;
  for (const match of text.matchAll(LINK)) {
    const [whole, label = "", href = ""] = match;
    found.push(...boldSpans(text.slice(from, match.index)), { text: label, strong: false, href });
    from = match.index + whole.length;
  }
  return [...found, ...boldSpans(text.slice(from))].filter((span) => span.text !== "");
}

export function parseMarkdown(markdown: string): Block[] {
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

/** Fills each {blank} with its value; a blank without one stays as written. */
export function fillBlanks(text: string, values: Readonly<Record<string, string>>): string {
  return text.replace(/\{(\w+)\}/gu, (whole, name: string) => values[name] ?? whole);
}

/** The names of a text's {blanks}. */
export function blanksIn(text: string): Set<string> {
  return new Set(Array.from(text.matchAll(/\{(\w+)\}/gu), (match) => match[1] ?? ""));
}
