import type { Schemas } from "@pg-platform/api-client";
import { getTranslations } from "next-intl/server";

import { cn } from "@/lib/utils";

type Status = Schemas["BookingStatus"];

/** Where the token is, by the booking's status. A booking that has ended shows no track. */
const PLACE: Partial<Record<Status, 0 | 1 | 2>> = {
  held: 0,
  token_secured: 1,
  confirmed: 1,
  checked_in: 1,
  disputed: 1,
  active: 2,
  completed: 2,
};

/**
 * The stay simulator's track, live: this booking's token, at the stop its status says. Drawn on the
 * server, so it needs no script. The amount is the booking's own, as the API gave it.
 */
export async function TokenTrack({ status, token }: { status: Status; token: string }) {
  const place = PLACE[status];
  if (place === undefined) return null;
  const [t, tSim] = await Promise.all([getTranslations("Bookings"), getTranslations("Home.sim")]);
  const stops = [tSim("you"), tSim("held"), tSim("rent")];
  return (
    <section aria-labelledby="token-track" className="rounded-[2rem] bg-surface-warm p-6 sm:p-8">
      <h2 id="token-track" className="text-title-3 font-medium">
        {t("tokenTrack")}
      </h2>
      <div className="sim-track mt-6" style={{ "--place": place }}>
        <div aria-hidden="true" className="sim-line rounded-full bg-input/50" />
        <div aria-hidden="true" className="sim-fill rounded-full bg-sun" />
        <ol className="m-0 list-none p-0">
          {stops.map((label, position) => (
            <li
              key={label}
              aria-current={position === place ? "step" : undefined}
              className="sim-stop flex flex-col items-center text-center"
              style={{ "--stop": position }}
            >
              <span aria-hidden="true" className="sim-node rounded-full bg-input" />
              <span
                className={cn(
                  "sim-label px-1 text-sm leading-snug font-medium",
                  position === place ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {label}
              </span>
            </li>
          ))}
        </ol>
        <div aria-hidden="true" className="sim-coin flex justify-center">
          <span className="grid size-(--coin) place-items-center rounded-full bg-sun text-center text-base font-bold text-sun-foreground shadow-lg ring-4 ring-surface-warm sm:text-xl">
            {token}
          </span>
        </div>
      </div>
    </section>
  );
}
