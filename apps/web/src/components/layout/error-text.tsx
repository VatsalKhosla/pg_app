"use client";

import { createContext, type ReactNode, use } from "react";

/**
 * The error page's text. Error boundaries must be client components, so the root layout
 * translates this on the server and hands it down: the browser then needs no message formatter.
 */
export interface ErrorText {
  title: string;
  body: string;
  retry: string;
  referenceLabel: string;
}

const ErrorTextContext = createContext<ErrorText | null>(null);

export function ErrorTextProvider({ text, children }: { text: ErrorText; children: ReactNode }) {
  return <ErrorTextContext value={text}>{children}</ErrorTextContext>;
}

export function useErrorText(): ErrorText {
  const text = use(ErrorTextContext);
  if (text === null) {
    throw new Error("useErrorText needs an ErrorTextProvider above it (the root layout has one)");
  }
  return text;
}
