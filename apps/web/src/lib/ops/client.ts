import type { Schemas } from "@pg-platform/api-client";

import { browserApi } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { withCsrf } from "@/lib/api/csrf";

/**
 * The ops console's calls from the browser (ADR 0023). Every change answers with the whole
 * listing as it now stands. Pages read through the server's client; these are for the forms.
 */

export type Listing = Schemas["ListingInfo"];
export type ListingCreated = Schemas["ListingCreated"];
export type Owner = Schemas["OwnerInfo"];
export type PropertyCreate = Schemas["PropertyCreate"];
export type PropertyUpdate = Schemas["PropertyUpdate"];
export type CategoryCreate = Schemas["CategoryCreate"];
export type CategoryUpdate = Schemas["CategoryUpdate"];
export type ListingStatus = Schemas["StatusChange"]["status"];

export function findOwners(q: string): Promise<Schemas["OwnerPage"]> {
  return unwrap(browserApi.GET("/v1/ops/owners", { params: { query: { q, limit: 10 } } }));
}

export function addOwner(body: Schemas["OwnerCreate"]): Promise<Owner> {
  return withCsrf((headers) => unwrap(browserApi.POST("/v1/ops/owners", { body, headers })));
}

export function createListing(body: PropertyCreate): Promise<ListingCreated> {
  return withCsrf((headers) => unwrap(browserApi.POST("/v1/ops/properties", { body, headers })));
}

export function updateListing(id: string, body: PropertyUpdate): Promise<Listing> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.PATCH("/v1/ops/properties/{property_id}", {
        params: { path: { property_id: id } },
        body,
        headers,
      }),
    ),
  );
}

export function setStatus(id: string, status: ListingStatus): Promise<Listing> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/properties/{property_id}/status", {
        params: { path: { property_id: id } },
        body: { status },
        headers,
      }),
    ),
  );
}

export function setAmenities(id: string, amenities: string[]): Promise<Listing> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.PUT("/v1/ops/properties/{property_id}/amenities", {
        params: { path: { property_id: id } },
        body: { amenities },
        headers,
      }),
    ),
  );
}

export function setMedia(id: string, media: string[]): Promise<Listing> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.PUT("/v1/ops/properties/{property_id}/media", {
        params: { path: { property_id: id } },
        body: { media },
        headers,
      }),
    ),
  );
}

export function addCategory(id: string, body: CategoryCreate): Promise<Listing> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/properties/{property_id}/room-categories", {
        params: { path: { property_id: id } },
        body,
        headers,
      }),
    ),
  );
}

export function updateCategory(categoryId: string, body: CategoryUpdate): Promise<Listing> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.PATCH("/v1/ops/room-categories/{category_id}", {
        params: { path: { category_id: categoryId } },
        body,
        headers,
      }),
    ),
  );
}

export function addRoom(categoryId: string, body: Schemas["RoomCreate"]): Promise<Listing> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/room-categories/{category_id}/rooms", {
        params: { path: { category_id: categoryId } },
        body,
        headers,
      }),
    ),
  );
}

export function addBed(roomId: string, label: string): Promise<Listing> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/rooms/{room_id}/beds", {
        params: { path: { room_id: roomId } },
        body: { label },
        headers,
      }),
    ),
  );
}

export function setBedStatus(
  bedId: string,
  status: Schemas["BedUpdate"]["status"],
): Promise<Listing> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.PATCH("/v1/ops/beds/{bed_id}", {
        params: { path: { bed_id: bedId } },
        body: { status },
        headers,
      }),
    ),
  );
}

// Verification (ADR 0024): ops book and cancel visits and suspend; field agents report.

export type Visit = Schemas["VisitInfo"];
export type ReportSubmit = Schemas["ReportSubmit"];

export function bookVisit(listingId: string, agent: string, scheduledFor: string): Promise<Visit> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/properties/{property_id}/verification-visits", {
        params: { path: { property_id: listingId } },
        body: { agent, scheduledFor },
        headers,
      }),
    ),
  );
}

export function cancelVisit(visitId: string, reason: string): Promise<Visit> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/verification-visits/{visit_id}/cancel", {
        params: { path: { visit_id: visitId } },
        body: { reason },
        headers,
      }),
    ),
  );
}

export function suspendVerification(listingId: string, reason: string): Promise<Listing> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/properties/{property_id}/verification/suspend", {
        params: { path: { property_id: listingId } },
        body: { reason },
        headers,
      }),
    ),
  );
}

export function submitReport(visitId: string, body: ReportSubmit): Promise<Visit> {
  return withCsrf((headers) =>
    unwrap(
      browserApi.POST("/v1/ops/verification-visits/{visit_id}/report", {
        params: { path: { visit_id: visitId } },
        body,
        headers,
      }),
    ),
  );
}
