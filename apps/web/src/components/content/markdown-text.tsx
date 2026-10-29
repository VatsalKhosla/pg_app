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
  2: { tag: "h2", className: "text-xl font-semibold tracking-tight" },
  3: { tag: "h3", className: "pt-2 text-lg font-semibold" },
  4: { tag: "h4", className: "font-semibold" },
} as const;

function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case "heading": {
      // The page's own heading is the h1: the text's headings sit one level below it.
      const { tag: Tag, className } = HEADINGS[(block.level + 1) as 2 | 3 | 4];
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

/** A long text in Markdown (the owner agreement, a legal page), laid out to read. */
export function MarkdownText({ text, ...props }: { text: string } & React.ComponentProps<"div">) {
  return (
    <div className="space-y-4" {...props}>
      {parseMarkdown(text).map((block, index) => (
        <BlockView key={index} block={block} />
      ))}
    </div>
  );
}
