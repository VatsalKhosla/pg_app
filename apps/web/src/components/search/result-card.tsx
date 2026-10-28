"use client";

import type { SearchCard } from "@/lib/search/client";

import { PgCard } from "./pg-card";

/** One PG in search's list: its card, which also lights up its pin on the map. */
export function ResultCard({
  card,
  active,
  onHover,
  first = false,
}: {
  card: SearchCard;
  active: boolean;
  onHover: (id: string | null) => void;
  first?: boolean;
}) {
  return (
    <PgCard
      card={card}
      active={active}
      first={first}
      handlers={{
        onMouseEnter: () => {
          onHover(card.id);
        },
        onMouseLeave: () => {
          onHover(null);
        },
        onFocus: () => {
          onHover(card.id);
        },
        onBlur: () => {
          onHover(null);
        },
      }}
    />
  );
}
