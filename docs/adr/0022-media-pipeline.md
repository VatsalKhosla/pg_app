# ADR 0022: Media: uploads straight to storage, cleaned by the worker before anyone sees them

- Status: accepted
- Date: 2026-10-21
- Build step: 2.3 (media pipeline)

## Context

Listings live on their photos and videos, and the ops console (step 2.4) uploads them from a phone. Phones put a lot in their files:
- the GPS position, which would give away the exact building that the display location hides (ADR 0021);
- the time and the camera;
- in videos, a location atom.

Documents (licences, agreements, KYC) must never be public. ARCHITECTURE §13 sets the rules:
- presigned uploads, with a type allowlist and size limits;
- magic bytes checked, and EXIF and GPS stripped, in the worker;
- WebP and AVIF variants;
- a poster and a duration limit for video;
- public media through the CDN, and private files behind short-lived signed URLs.

## Decision

1. **The file never passes through the API.**
   - `POST /v1/media` (staff, in a staff session, for now) creates an asset and returns a **presigned POST**. The browser posts the file straight to storage.
   - **Storage enforces the policy itself:** the declared content type and the purpose's size limit (photos 15 MB, video 200 MB, documents 10 MB), for 15 minutes. SeaweedFS, which runs locally, enforces both, as S3 does.
   - `POST /v1/media/{id}/uploaded` then checks with storage, before locking any row, that the file is there, and queues it for the worker.
2. **Two buckets.**
   - **The private one** holds every upload as it arrived (`uploads/…`) and the processed private files (`files/…`).
   - **The public one** holds only processed listing media (`media/…`), read through the CDN. Locally, a bucket policy lets anyone read `media/*`, as the CDN will.
   - **Originals never become public.** An original still has its metadata, so a second job deletes it once the result has committed, never before. A failed attempt can then try again.
3. **The worker cleans everything** (`app/modules/media/processing.py`, in a thread):
   - **The real type** must match the claimed one: JPEG, PNG, WebP, MP4 or PDF, checked by signature. A mismatch is rejected with its reason.
   - **Photos:**
     - **Size first:** the pixel count is checked before decoding (50 megapixels at most), so a small file can't expand into a huge one.
     - **Upright, and bare:** turned upright, then stripped of every metadata entry but the colour profile. That means no EXIF, so no GPS or camera, and no XMP.
     - **Variants:** re-encoded as WebP and AVIF at four sizes, the longest edge 160, 480, 1080 and 2048 px, never enlarged.
     - **Capture time:** read from EXIF before stripping (India's time when the file gives no offset), and only kept if plausible.
   - **Videos** are remuxed, not re-encoded, into a new MP4 that holds only their video and audio. The container and stream metadata (phones write the location there as a `loci` atom), and any data tracks, are left behind. The new file starts playing before it has downloaded (faststart). A poster frame, from one second in and turned upright, gets the photo variants. Videos over 3 minutes are refused.
   - **Documents** that are images are re-encoded the same way. PDFs are kept as they are, and are only ever downloaded (`Content-Disposition: attachment`), never shown inline.
   - **Tests** check every variant byte by byte for EXIF, GPS, XMP and the camera, and the cleaned video for its location.
4. **Serving:**
   - **Public files:** at their CDN address, cached for a year (`immutable`), since a new upload gets a new id.
   - **Private files:** only through links signed for 5 minutes, which the API makes when asked.
   - **Who may look:** the uploader, or ops and admins (anyone else gets a 404).
5. **`verified_capture`** marks a listing photo or video a field agent took. The page shows "Verified photo · <capture date>". Staff uploads need no moderation; owners' and students' uploads will wait for review.
6. **HEIC is not accepted.** Browsers hand iPhone photos over as JPEG when a page doesn't accept HEIC, and decoding HEIC would need libheif with an HEVC decoder, which raises licensing questions the founders haven't been asked.
7. **Dependencies and ports:**
   - **The `ObjectStorage` port** has an S3 adapter (boto3, with blocking calls in threads, connect 3 s, read 10 s, standard retries), which serves AWS and SeaweedFS.
   - **Pillow 13.0** has AVIF built in. It is taken past the cooldown (ADR 0007) because 12.3 has a heap overflow in its JPEG decoder (CVE-2026-112403, critical) and eight more decoder bugs. `Image.open` is also limited to the JPEG, PNG and WebP decoders, so no other format's parser ever runs on an upload.
   - **PyAV 19** bundles FFmpeg. Its wheels are a GPL build (they include x264 and x265). We only decode and remux, in our own worker, and never distribute FFmpeg, which the GPL allows. Revisit if the image is ever distributed.
   - **Local buckets:** `python -m app.manage media buckets` creates them (it runs in `make seed`). In deployed environments, Terraform does.

## Consequences

- **Step 2.4** attaches assets to listings (order and cover) and uploads from the phone with the presigned form. The private bucket's CORS allows the web origin's POSTs.
- **CPU:** a photo costs the worker about a second of CPU per variant at full size. Heavy upload days need more worker capacity, or a separate media worker later.
- **Moderation queues** for owner and student uploads arrive with the features that need them.
- **Deploying** needs:
  - the two buckets;
  - the CDN in front of the public one;
  - an IAM role for the API and worker (no keys);
  - a lifecycle rule as a backstop for stale `uploads/` objects.
