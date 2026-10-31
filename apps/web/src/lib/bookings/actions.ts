import type { BookingStatus, StudentBooking } from "./client";

/** Ended without a stay: the student may want help finding another PG. */
const ENDED_EARLY: readonly BookingStatus[] = [
  "expired",
  "cancelled",
  "rejected",
  "no_show",
  "refunded",
];
/** Confirmed, and on from there: the owner's phone and the address show (CLAUDE.md rule 11). */
const CONFIRMED_ONWARDS: readonly BookingStatus[] = [
  "confirmed",
  "checked_in",
  "disputed",
  "active",
  "completed",
];

export interface BookingActions {
  /** Cancel, with the refund the API says cancelling now gives back. */
  cancel: boolean;
  findAnother: boolean;
  contact: boolean;
}

/**
 * What a student can do with a booking in its state (step 5.5): the API says whether it can be
 * cancelled now (and what that gives back); everything else follows from the status.
 */
export function actionsFor(
  booking: Pick<StudentBooking, "status" | "cancellation">,
): BookingActions {
  return {
    cancel: booking.cancellation !== null,
    findAnother: ENDED_EARLY.includes(booking.status),
    contact: CONFIRMED_ONWARDS.includes(booking.status),
  };
}
