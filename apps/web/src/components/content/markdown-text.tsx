import type { Route } from "next";
import Link from "next/link";
import type * as React from "react";

import { type Block, parseMarkdown, type Span } from "@/lib/content/markdown";

function Spans({ content }: { content: Span[] }) {
  return content.map((span, index) => {
    if (span.href !== undefined) {
      return (
        <Link
          key={index}
          href={span.href as Route}
          className="font-medium text-primary underline underline-offset-4"
        >
          {span.text}
        </Link>
      );
    }
    return span.strong ? (
      <strong key={index} className="font-semibold">
        {span.text}
      </strong>
    ) : (
      <span key={index}>{span.text}</span>
    );
  });
}

const HEADINGS = {
  2: { tag: "h2", className: "pt-2 text-title-3 font-semibold tracking-tight text-foreground" },
  3: { tag: "h3", className: "pt-2 text-lg font-semibold text-foreground" },
  4: { tag: "h4", className: "font-semibold text-foreground" },
  5: { tag: "h5", className: "font-semibold text-foreground" },
} as const;

function BlockView({ block, depth }: { block: Block; depth: 1 | 2 }) {
  switch (block.kind) {
    case "heading": {
      // The page's own heading is the h1: the text's headings sit ``depth`` levels below it.
      const { tag: Tag, className } = HEADINGS[(block.level + depth) as 2 | 3 | 4 | 5];
      return (
        <Tag className={className}>
          <Spans content={block.content} />
        </Tag>
      );
    }
    case "paragraph":
      return (
        <p className="leading-7">
          <Spans content={block.content} />
        </p>
      );
    case "list":
      return (
        <ul className="list-disc space-y-2 pl-5 leading-7">
          {block.items.map((item, index) => (
            <li key={index}>
              <Spans content={item} />
            </li>
          ))}
        </ul>
      );
  }
}

/**
 * A long text in Markdown (the owner agreement, a legal page), laid out to read. ``depth`` 2 puts
 * its headings one level further down, for a text inside a section with a heading of its own (a
 * booking's rent agreement).
 */
export function MarkdownText({
  text,
  depth = 1,
  ...props
}: { text: string; depth?: 1 | 2 } & React.ComponentProps<"div">) {
  return (
    <div className="space-y-4" {...props}>
      {parseMarkdown(text).map((block, index) => (
        <BlockView key={index} block={block} depth={depth} />
      ))}
    </div>
  );
}
