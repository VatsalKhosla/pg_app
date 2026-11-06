"use client";

import { useId, useState } from "react";

import { useRefresh } from "@/components/ops/use-refresh";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { upload } from "@/lib/media/client";
import { addDocument, type DocumentKind } from "@/lib/owner/browser";

export interface DocumentUploadText {
  title: string;
  kind: string;
  file: string;
  submit: string;
  working: string;
  done: string;
  refused: string;
  failed: string;
  needFile: string;
}

const ACCEPT = "application/pdf,image/jpeg,image/png";

/**
 * An owner adds a licence or society permission to their PG (step 7.1): the file goes straight
 * to private storage, is checked, and joins the PG's documents for ops to look at.
 */
export function DocumentUpload({
  propertyId,
  kinds,
  text,
}: {
  propertyId: string;
  kinds: readonly { value: DocumentKind; label: string }[];
  text: DocumentUploadText;
}) {
  const refresh = useRefresh();
  const formId = useId();
  const [kind, setKind] = useState<DocumentKind>(kinds[0]?.value ?? "licence");
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<"idle" | "working" | "done">("idle");
  const [problem, setProblem] = useState<string | null>(null);

  async function send() {
    if (file === null) {
      setProblem(text.needFile);
      return;
    }
    setProblem(null);
    setState("working");
    try {
      const media = await upload("document", file);
      if (media?.status !== "ready") {
        setProblem(text.refused);
        setState("idle");
        return;
      }
      await addDocument(propertyId, kind, media.id);
      setState("done");
      setFile(null);
      refresh();
    } catch {
      setProblem(text.failed);
      setState("idle");
    }
  }

  return (
    <section aria-labelledby={`${formId}-title`} className="space-y-3 rounded-lg border p-4">
      <h3 id={`${formId}-title`} className="font-semibold">
        {text.title}
      </h3>
      <Field id={`${formId}-kind`} label={text.kind}>
        {(control) => (
          <Select
            {...control}
            value={kind}
            onChange={(event) => {
              setKind(event.target.value as DocumentKind);
            }}
          >
            {kinds.map((each) => (
              <option key={each.value} value={each.value}>
                {each.label}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field id={`${formId}-file`} label={text.file}>
        {(control) => (
          <Input
            {...control}
            type="file"
            accept={ACCEPT}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setState("idle");
            }}
          />
        )}
      </Field>
      <Button
        disabled={state === "working"}
        onClick={() => {
          void send();
        }}
      >
        {text.submit}
      </Button>
      <p role="status" className="text-sm">
        {state === "working" ? text.working : state === "done" ? text.done : ""}
      </p>
      {problem === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {problem}
        </p>
      )}
    </section>
  );
}
