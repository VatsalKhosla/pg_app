"use client";

import { Printer } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Prints the page, which prints its document alone (globals.css). */
export function PrintButton({ label }: { label: string }) {
  return (
    <Button
      type="button"
      variant="outline"
      data-print-hidden
      onClick={() => {
        window.print();
      }}
    >
      <Printer aria-hidden />
      {label}
    </Button>
  );
}
