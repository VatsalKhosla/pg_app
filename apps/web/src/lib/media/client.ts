import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * Uploads from the browser (ADR 0022): start one, post the file straight to storage, say it's
 * done, then wait while the worker strips its metadata and makes its sizes.
 */

export type Media = Schemas["MediaInfo"];
export type Purpose = Schemas["UploadRequest"]["purpose"];

/** How long to wait for the worker to prepare a file before giving up on it. */
export const PROCESSING_TIMEOUT_MS = 5 * 60_000;

export function startUpload(purpose: Purpose, file: File): Promise<Schemas["UploadStarted"]> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/media", {
        body: { purpose, contentType: file.type, byteSize: file.size },
        headers,
      }),
    ),
  );
}

/** Post the file to storage with the presigned form: storage itself checks type and size. */
export async function sendToStorage(form: Schemas["UploadForm"], file: File): Promise<void> {
  const body = new FormData();
  for (const [name, value] of Object.entries(form.fields)) body.append(name, value);
  body.append("file", file);
  const response = await fetch(form.url, { method: "POST", body });
  if (!response.ok) throw new Error(`storage refused the file (${String(response.status)})`);
}

export function finishUpload(mediaId: string): Promise<Media> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/media/{media_id}/uploaded", {
        params: { path: { media_id: mediaId } },
        headers,
      }),
    ),
  );
}

export function getMedia(mediaId: string): Promise<Media> {
  return unwrap(
    browserApi.GET("/v1/media/{media_id}", { params: { path: { media_id: mediaId } } }),
  );
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/** Ask after the file until the worker has finished with it, more slowly as time goes on. */
export async function whenProcessed(mediaId: string): Promise<Media | null> {
  const started = Date.now();
  for (let delay = 1_000; Date.now() - started < PROCESSING_TIMEOUT_MS;) {
    await wait(delay);
    const media = await getMedia(mediaId);
    if (media.status !== "processing") return media;
    delay = Math.min(delay * 1.5, 5_000);
  }
  return null;
}

/**
 * Upload a file and wait for the worker: the file ready, or the reason it was refused. Null when
 * the worker took too long. Errors from the API or storage are thrown.
 */
export async function upload(
  purpose: Purpose,
  file: File,
  onProcessing?: () => void,
): Promise<Media | null> {
  const started = await startUpload(purpose, file);
  await sendToStorage(started.upload, file);
  await finishUpload(started.media.id);
  onProcessing?.();
  return whenProcessed(started.media.id);
}
