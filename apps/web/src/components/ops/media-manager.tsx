"use client";

import type { Schemas } from "@pg-platform/api-client";
import { ArrowDown, ArrowUp, BadgeCheck, ImagePlus, Star, Trash } from "lucide-react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  finishUpload,
  getMedia,
  type Listing,
  type Media,
  sendToStorage,
  setMedia,
  startUpload,
} from "@/lib/ops/client";

import { FormOutcome } from "./fields";
import { useOpsProblem } from "./problems";
import { useRefresh } from "./use-refresh";

type ListingMedia = Schemas["ListingMedia"];

/** What the API takes (apps/api/src/app/modules/media/domain/assets.py); it checks again. */
const ACCEPT = "image/jpeg,image/png,image/webp,video/mp4";
/** A listing's photos and videos at most (apps/api/src/app/modules/catalog/service/listings.py). */
const MAX_MEDIA = 40;
/** How long to wait for the worker to prepare a file before giving up on it. */
const PROCESSING_TIMEOUT_MS = 5 * 60_000;

type Upload =
  | { key: string; name: string; state: "uploading" }
  | { key: string; name: string; state: "processing" }
  | { key: string; name: string; state: "rejected" | "failed"; reason: string };

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/** Ask after the file until the worker has finished with it, more slowly as time goes on. */
async function whenProcessed(mediaId: string): Promise<Media | null> {
  const started = Date.now();
  for (let delay = 1_000; Date.now() - started < PROCESSING_TIMEOUT_MS;) {
    await wait(delay);
    const media = await getMedia(mediaId);
    if (media.status !== "processing") return media;
    delay = Math.min(delay * 1.5, 5_000);
  }
  return null;
}

/** The picture to show for a photo, or a video's poster: the card-sized WebP. */
function pictureOf(media: ListingMedia): Schemas["Rendition"] | undefined {
  const images = media.renditions.filter((rendition) => rendition.contentType.startsWith("image/"));
  return (
    images.find(
      (rendition) => rendition.name === "card" && rendition.contentType === "image/webp",
    ) ?? images[0]
  );
}

/**
 * A listing's photos and videos, in order: the first is the cover. Files go straight to storage
 * (ADR 0022); the worker strips their metadata and makes the sizes, and each one joins the
 * listing once it's ready. Every change saves the whole order.
 */
export function MediaManager({ listing }: { listing: Listing }) {
  const t = useTranslations("Ops.media");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const inputId = useId();
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // The order as last saved. Changes queue up, so uploads finishing together each add to the
  // order the one before left, not to a stale copy.
  const order = useRef(listing.media.map((media) => media.id));
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  useEffect(() => {
    order.current = listing.media.map((media) => media.id);
  }, [listing.media]);

  function save(change: (ids: string[]) => string[]): Promise<void> {
    const run = queue.current.then(async () => {
      const saved = await setMedia(listing.id, change(order.current));
      order.current = saved.media.map((media) => media.id);
      refresh();
    });
    queue.current = run.catch(() => undefined);
    return run;
  }

  async function reorder(change: (ids: string[]) => string[]) {
    setFailure(null);
    setSaving(true);
    try {
      await save(change);
    } catch (error) {
      setFailure(problem(error));
    } finally {
      setSaving(false);
    }
  }

  function track(key: string, next: Upload | null) {
    setUploads((current) => {
      const others = current.filter((upload) => upload.key !== key);
      return next === null ? others : [...others, next];
    });
  }

  async function upload(file: File) {
    const key = crypto.randomUUID();
    const name = file.name;
    track(key, { key, name, state: "uploading" });
    try {
      const purpose = file.type.startsWith("video/") ? "listing_video" : "listing_photo";
      const started = await startUpload(purpose, file);
      await sendToStorage(started.upload, file);
      await finishUpload(started.media.id);
      track(key, { key, name, state: "processing" });
      const processed = await whenProcessed(started.media.id);
      if (processed === null) {
        track(key, { key, name, state: "failed", reason: t("tooSlow") });
      } else if (processed.status === "rejected") {
        track(key, { key, name, state: "rejected", reason: processed.rejectionReason ?? "" });
      } else {
        await save((ids) => [...ids, processed.id]);
        track(key, null);
      }
    } catch (error) {
      track(key, { key, name, state: "failed", reason: problem(error) });
    }
  }

  const media = listing.media;
  const room =
    MAX_MEDIA -
    media.length -
    uploads.filter((item) => item.state !== "rejected" && item.state !== "failed").length;

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">{t("intro")}</p>
      {media.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("empty")}</p>
      ) : (
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {media.map((item, index) => {
            const picture = pictureOf(item);
            const label =
              item.purpose === "listing_video"
                ? t("video", { number: index + 1 })
                : t("photo", { number: index + 1 });
            return (
              <li key={item.id} className="space-y-2 rounded-md border p-2">
                <div className="relative aspect-[4/3] overflow-hidden rounded bg-muted">
                  {picture === undefined ? (
                    <p className="p-3 text-sm text-muted-foreground">{t("preparing")}</p>
                  ) : (
                    <Image
                      src={picture.url}
                      alt={label}
                      fill
                      unoptimized
                      sizes="(min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
                      className="object-cover"
                    />
                  )}
                </div>
                <p className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium">{label}</span>
                  {index === 0 ? (
                    <span className="rounded-full bg-primary px-2 py-0.5 text-xs text-primary-foreground">
                      {t("cover")}
                    </span>
                  ) : null}
                  {item.verifiedCapture ? (
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      <BadgeCheck aria-hidden className="size-4" />
                      {t("verified")}
                    </span>
                  ) : null}
                </p>
                <div className="flex flex-wrap gap-1">
                  {index > 0 ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={saving}
                      onClick={() => {
                        void reorder((ids) => [
                          item.id,
                          ...ids.filter((other) => other !== item.id),
                        ]);
                      }}
                    >
                      <Star aria-hidden />
                      {t("makeCover", { item: label })}
                    </Button>
                  ) : null}
                  {index > 0 ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={saving}
                      onClick={() => {
                        void reorder((ids) => moved(ids, item.id, -1));
                      }}
                    >
                      <ArrowUp aria-hidden />
                      {t("moveUp", { item: label })}
                    </Button>
                  ) : null}
                  {index < media.length - 1 ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={saving}
                      onClick={() => {
                        void reorder((ids) => moved(ids, item.id, 1));
                      }}
                    >
                      <ArrowDown aria-hidden />
                      {t("moveDown", { item: label })}
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={saving}
                    onClick={() => {
                      void reorder((ids) => ids.filter((other) => other !== item.id));
                    }}
                  >
                    <Trash aria-hidden />
                    {t("remove", { item: label })}
                  </Button>
                </div>
              </li>
            );
          })}
        </ol>
      )}

      {uploads.length === 0 ? null : (
        <ul aria-live="polite" className="space-y-1 text-sm">
          {uploads.map((item) => (
            <li
              key={item.key}
              className={
                item.state === "rejected" || item.state === "failed"
                  ? "text-destructive"
                  : "text-muted-foreground"
              }
            >
              {item.state === "uploading"
                ? t("uploading", { name: item.name })
                : item.state === "processing"
                  ? t("processing", { name: item.name })
                  : t(item.state, { name: item.name, reason: item.reason })}
            </li>
          ))}
        </ul>
      )}
      <FormOutcome failure={failure} />

      {room > 0 ? (
        <div>
          <input
            id={inputId}
            type="file"
            accept={ACCEPT}
            multiple
            className="peer sr-only"
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []).slice(0, room);
              event.target.value = "";
              for (const file of files) void upload(file);
            }}
          />
          <label
            htmlFor={inputId}
            className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-md border bg-background px-6 text-sm font-medium shadow-xs hover:bg-accent peer-focus-visible:ring-[3px] peer-focus-visible:ring-ring/50"
          >
            <ImagePlus aria-hidden className="size-4" />
            {t("add")}
          </label>
        </div>
      ) : null}
    </div>
  );
}

/** `ids` with `id` moved one place earlier (-1) or later (1). */
function moved(ids: string[], id: string, step: -1 | 1): string[] {
  const from = ids.indexOf(id);
  const to = from + step;
  if (from === -1 || to < 0 || to >= ids.length) return ids;
  const next = ids.filter((other) => other !== id);
  next.splice(to, 0, id);
  return next;
}
