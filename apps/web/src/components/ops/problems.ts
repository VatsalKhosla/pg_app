"use client";

import { useMessages } from "next-intl";
import { useCallback } from "react";

import { problemMessage } from "@/components/auth/problem-message";

/**
 * Codes whose message the API completes with what it found ("That doesn't work: the deposit is
 * more than three months' rent"). The detail is the API's, in English: the console is for staff.
 */
const WITH_DETAIL: readonly string[] = [
  "LISTING_INVALID",
  "LISTING_INCOMPLETE",
  "MEDIA_NOT_ALLOWED",
  "RULE_SET_INVALID",
  "QUOTE_INVALID",
  "BLOCK_INVALID",
  "BED_UNAVAILABLE",
];

/** What to tell ops about a failed call, from the console's own messages. */
export function useOpsProblem(): (error: unknown) => string {
  const messages: Record<string, string> = useMessages().Ops.errors;
  return useCallback((error) => problemMessage(error, messages, WITH_DETAIL), [messages]);
}
