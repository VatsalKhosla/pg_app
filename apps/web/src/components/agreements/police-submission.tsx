"use client";

import { BadgeCheck, FileUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { problemMessage } from "@/components/auth/problem-message";
import { Button } from "@/components/ui/button";
import { Field, FormOutcome } from "@/components/ui/fields";
import { Input } from "@/components/ui/input";
import { markSubmitted, markVerified } from "@/lib/agreements/client";
import { upload } from "@/lib/media/client";

export interface PoliceSubmissionText {
  title: string;
  intro: string;
  file: string;
  fileHint: string;
  reference: string;
  submit: string;
  submitting: string;
  uploading: string;
  needFile: string;
  refused: string;
  tooSlow: string;
  verify: string;
  verifyHint: string;
  verifying: string;
  errors: Record<string, string>;
}

// What a document may be (ADR 0022): a PDF or a photo of one, up to 10 MB.
const ACCEPT = "application/pdf,image/jpeg,image/png";

/**
 * The owner's side of a tenant's police verification (ADR 0070): once they've submitted the
 * details on the Delhi Police portal, they upload the acknowledgement it gives (a private
 * document) with its number, and later say the police have verified the tenant.
 */
export function PoliceSubmission({
  code,
  canMarkSubmitted,
  canMarkVerified,
  text,
}: {
  code: string;
  canMarkSubmitted: boolean;
  canMarkVerified: boolean;
  text: PoliceSubmissionText;
}) {
  const id = useId();
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [reference, setReference] = useState("");
  const [needFile, setNeedFile] = useState(false);
  const [busy, setBusy] = useState<"uploading" | "saving" | "verifying" | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function submit() {
    if (file === null) {
      setNeedFile(true);
      return;
    }
    setNeedFile(false);
    setFailure(null);
    try {
      setBusy("uploading");
      const ready = await upload("document", file);
      if (ready === null) {
        setFailure(text.tooSlow);
        return;
      }
      if (ready.status === "rejected") {
        setFailure(text.refused.replace("{reason}", ready.rejectionReason ?? ""));
        return;
      }
      setBusy("saving");
      const trimmed = reference.trim();
      await markSubmitted(code, {
        acknowledgement: ready.id,
        ...(trimmed === "" ? {} : { reference: trimmed }),
      });
      router.refresh();
    } catch (error) {
      setFailure(problemMessage(error, text.errors));
    } finally {
      setBusy(null);
    }
  }

  async function verify() {
    setFailure(null);
    setBusy("verifying");
    try {
      await markVerified(code);
      router.refresh();
    } catch (error) {
      setFailure(problemMessage(error, text.errors));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div
      data-print-hidden
      className="space-y-4 rounded-2xl border border-primary/30 bg-primary-soft/50 p-5"
    >
      {canMarkSubmitted ? (
        <form
          method="post"
          noValidate
          aria-labelledby={`${id}-title`}
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="space-y-1.5">
            <h3 id={`${id}-title`} className="font-semibold text-foreground">
              {text.title}
            </h3>
            <p className="text-sm text-muted-foreground">{text.intro}</p>
          </div>
          <Field
            id={`${id}-file`}
            label={text.file}
            hint={text.fileHint}
            error={needFile ? text.needFile : undefined}
          >
            {(control) => (
              <Input
                {...control}
                type="file"
                accept={ACCEPT}
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                }}
              />
            )}
          </Field>
          <Field id={`${id}-reference`} label={text.reference}>
            {(control) => (
              <Input
                {...control}
                maxLength={60}
                value={reference}
                onChange={(event) => {
                  setReference(event.target.value);
                }}
              />
            )}
          </Field>
          <Button type="submit" disabled={busy !== null}>
            <FileUp aria-hidden />
            {busy === "uploading"
              ? text.uploading
              : busy === "saving"
                ? text.submitting
                : text.submit}
          </Button>
        </form>
      ) : null}
      {canMarkVerified ? (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">{text.verifyHint}</p>
          <Button type="button" disabled={busy !== null} onClick={() => void verify()}>
            <BadgeCheck aria-hidden />
            {busy === "verifying" ? text.verifying : text.verify}
          </Button>
        </div>
      ) : null}
      <FormOutcome failure={failure} />
    </div>
  );
}
