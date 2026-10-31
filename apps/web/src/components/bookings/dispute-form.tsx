"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ImagePlus, Trash } from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/components/auth/problem-message";
import { Button } from "@/components/ui/button";
import { Choices, Field, FormOutcome, Textarea } from "@/components/ui/fields";
import { ApiError } from "@/lib/api/errors";
import { openDispute } from "@/lib/bookings/client";
import { z } from "@/lib/forms/zod";
import { upload } from "@/lib/media/client";

const REASONS = ["not_as_shown", "unsafe", "other"] as const;
// The API's limits (ADR 0051).
const MAX_PHOTOS = 6;
const DESCRIPTION_MIN = 10;
const DESCRIPTION_MAX = 2_000;
const ACCEPT = "image/jpeg,image/png,image/webp";

interface Photo {
  id: string;
  thumbnail: string | undefined;
}

type Upload =
  | { key: string; name: string; state: "uploading" | "processing" }
  | { key: string; name: string; state: "failed"; reason: string };

/**
 * "The room isn't as shown" (step 5.7, ADR 0051): while their time to check the room lasts, a
 * student says why, in their own words, with up to six photos. The photos are private: only the
 * student and our team see them. Sending it puts the booking on hold for our team, and the owner
 * hears.
 */
export function DisputeForm({ code }: { code: string }) {
  const t = useTranslations("Bookings.dispute");
  const id = useId();
  const router = useRouter();
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    reason: z.enum(REASONS, { error: t("needReason") }),
    description: z
      .string()
      .trim()
      .min(DESCRIPTION_MIN, t("needDescription"))
      .max(DESCRIPTION_MAX, t("needDescription")),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { description: "" },
  });
  const { errors, isSubmitting } = form.formState;
  const busy = uploads.some((item) => item.state !== "failed");

  function track(key: string, next: Upload | null) {
    setUploads((current) => {
      const others = current.filter((item) => item.key !== key);
      return next === null ? others : [...others, next];
    });
  }

  async function add(file: File) {
    const key = crypto.randomUUID();
    track(key, { key, name: file.name, state: "uploading" });
    try {
      const ready = await upload("dispute_photo", file, () => {
        track(key, { key, name: file.name, state: "processing" });
      });
      if (ready?.status !== "ready") {
        const reason = ready === null ? t("tooSlow") : (ready.rejectionReason ?? "");
        track(key, { key, name: file.name, state: "failed", reason });
        return;
      }
      const thumbnail = ready.renditions.find((rendition) => rendition.name === "thumb")?.url;
      setPhotos((current) => [...current, { id: ready.id, thumbnail }]);
      track(key, null);
    } catch (error) {
      track(key, {
        key,
        name: file.name,
        state: "failed",
        reason: problemMessage(error, { generic: t("uploadFailed") }),
      });
    }
  }

  async function send(values: Values) {
    setFailure(null);
    try {
      await openDispute(code, { ...values, photos: photos.map((photo) => photo.id) });
      router.refresh();
    } catch (error) {
      if (error instanceof ApiError && error.code === "INVALID_TRANSITION") {
        setFailure(t("tooLate"));
        router.refresh();
        return;
      }
      setFailure(
        problemMessage(error, { generic: t("failed"), DISPUTE_INVALID: t("photosRefused") }),
      );
    }
  }

  return (
    <form
      noValidate
      aria-labelledby={`${id}-title`}
      className="space-y-5 rounded-lg border p-4"
      onSubmit={(event) => {
        void form.handleSubmit(send)(event);
      }}
    >
      <div className="space-y-1">
        <h3 id={`${id}-title`} className="font-semibold">
          {t("title")}
        </h3>
        <p className="text-sm text-muted-foreground">{t("intro")}</p>
      </div>
      <Choices
        id={`${id}-reason`}
        legend={t("reason")}
        options={REASONS.map((reason) => ({ value: reason, label: t(`reasons.${reason}`) }))}
        registration={form.register("reason")}
        error={errors.reason?.message}
        columns={3}
      />
      <Field
        id={`${id}-description`}
        label={t("description")}
        hint={t("descriptionHint")}
        error={errors.description?.message}
      >
        {(control) => (
          <Textarea
            {...control}
            rows={4}
            maxLength={DESCRIPTION_MAX}
            {...form.register("description")}
          />
        )}
      </Field>
      <fieldset className="space-y-3">
        <legend className="text-sm font-medium">{t("photos")}</legend>
        <p className="text-sm text-muted-foreground">{t("photosHint")}</p>
        {photos.length === 0 ? null : (
          <ol className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {photos.map((photo, index) => (
              <li key={photo.id} className="space-y-1">
                <div className="relative aspect-square overflow-hidden rounded bg-muted">
                  {photo.thumbnail === undefined ? null : (
                    <Image
                      src={photo.thumbnail}
                      alt={t("photo", { number: index + 1 })}
                      fill
                      unoptimized
                      sizes="160px"
                      className="object-cover"
                    />
                  )}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setPhotos((current) => current.filter((other) => other.id !== photo.id));
                  }}
                >
                  <Trash aria-hidden />
                  {t("removePhoto", { number: index + 1 })}
                </Button>
              </li>
            ))}
          </ol>
        )}
        {uploads.length === 0 ? null : (
          <ul aria-live="polite" className="space-y-1 text-sm">
            {uploads.map((item) => (
              <li
                key={item.key}
                className={item.state === "failed" ? "text-destructive" : "text-muted-foreground"}
              >
                {item.state === "failed"
                  ? t("photoFailed", { name: item.name, reason: item.reason })
                  : t(item.state, { name: item.name })}
              </li>
            ))}
          </ul>
        )}
        {photos.length < MAX_PHOTOS ? (
          <div>
            <input
              id={`${id}-photos`}
              type="file"
              accept={ACCEPT}
              multiple
              className="peer sr-only"
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []).slice(
                  0,
                  MAX_PHOTOS - photos.length,
                );
                event.target.value = "";
                for (const file of files) void add(file);
              }}
            />
            <label
              htmlFor={`${id}-photos`}
              className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-md border bg-background px-6 text-sm font-medium shadow-xs hover:bg-accent peer-focus-visible:ring-[3px] peer-focus-visible:ring-ring/50"
            >
              <ImagePlus aria-hidden className="size-4" />
              {t("addPhotos")}
            </label>
          </div>
        ) : null}
      </fieldset>
      <FormOutcome failure={failure} />
      <Button type="submit" variant="destructive" disabled={isSubmitting || busy}>
        {isSubmitting ? t("sending") : t("send")}
      </Button>
    </form>
  );
}
