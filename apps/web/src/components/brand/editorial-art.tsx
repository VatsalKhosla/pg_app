import { cn } from "@/lib/utils";

/**
 * Editorial SVG artwork and architectural motifs inspired by modern Indian residences
 * (arches, terracotta facades, sunlit courtyards, botanical foliage and verified shields).
 * All decorative SVGs are hidden from assistive technology (`aria-hidden="true"`) and use
 * CSS design tokens from `globals.css` (`--primary`, `--ember`, `--marigold`, `--dusk`, `--neem`),
 * shipping zero client JavaScript and zero external network requests.
 */
export function HeroCourtyardArt({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "relative overflow-hidden rounded-3xl border border-ember-border/80 bg-surface-warm p-5 shadow-lg sm:p-7",
        className,
      )}
    >
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-full bg-ember" />
          <span className="size-2.5 rounded-full bg-marigold" />
          <span className="size-2.5 rounded-full bg-neem" />
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-8 rounded-full bg-primary/25" />
          <span className="h-2 w-4 rounded-full bg-dusk/25" />
        </div>
      </div>

      <svg
        viewBox="0 0 440 310"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="h-auto w-full rounded-2xl"
      >
        {/* Warm sky & sunlit backdrop */}
        <rect width="440" height="310" rx="18" fill="var(--marigold-soft)" />
        <circle cx="348" cy="68" r="44" fill="var(--marigold)" fillOpacity="0.28" />
        <circle cx="348" cy="68" r="26" fill="var(--ember)" fillOpacity="0.35" />

        {/* Distant Indigo skyline silhouette */}
        <path d="M0 190 L0 128 C28 128 32 104 62 104 L112 104 L112 190 Z" fill="var(--dusk-soft)" />
        <rect x="20" y="120" width="18" height="26" rx="9" fill="var(--dusk)" fillOpacity="0.22" />
        <rect x="48" y="120" width="18" height="26" rx="9" fill="var(--dusk)" fillOpacity="0.22" />

        {/* Main Terracotta & Sandstone Residence */}
        <rect
          x="74"
          y="62"
          width="244"
          height="210"
          rx="16"
          fill="var(--ember-soft)"
          stroke="var(--ember-border)"
          strokeWidth="2"
        />
        {/* Decorative parapet cornice */}
        <rect x="74" y="62" width="244" height="16" rx="6" fill="var(--ember)" fillOpacity="0.82" />

        {/* Upper floor arched windows (Jharokha motif) */}
        <g>
          <path
            d="M104 146 V112 C104 99 124 99 124 112 V146 Z"
            fill="var(--dusk-soft)"
            stroke="var(--dusk)"
            strokeWidth="1.75"
          />
          <path
            d="M148 146 V112 C148 99 168 99 168 112 V146 Z"
            fill="var(--marigold-soft)"
            stroke="var(--marigold)"
            strokeWidth="1.75"
          />
          <path
            d="M224 146 V112 C224 99 244 99 244 112 V146 Z"
            fill="var(--marigold-soft)"
            stroke="var(--marigold)"
            strokeWidth="1.75"
          />
          <path
            d="M268 146 V112 C268 99 288 99 288 112 V146 Z"
            fill="var(--dusk-soft)"
            stroke="var(--dusk)"
            strokeWidth="1.75"
          />
          {/* Balcony railings */}
          <line
            x1="98"
            y1="147"
            x2="174"
            y2="147"
            stroke="var(--ember)"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <line
            x1="218"
            y1="147"
            x2="294"
            y2="147"
            stroke="var(--ember)"
            strokeWidth="3"
            strokeLinecap="round"
          />
        </g>

        {/* Central Grand Courtyard Archway */}
        <path
          d="M154 272 V192 C154 162 238 162 238 192 V272 Z"
          fill="var(--primary-soft)"
          stroke="var(--primary)"
          strokeWidth="2.5"
        />
        <path
          d="M168 272 V198 C168 176 224 176 224 198 V272 Z"
          fill="var(--primary)"
          fillOpacity="0.16"
        />
        {/* Warm pendant lamp inside the archway */}
        <line x1="196" y1="169" x2="196" y2="192" stroke="var(--marigold)" strokeWidth="2" />
        <circle cx="196" cy="196" r="7" fill="var(--marigold)" />

        {/* Right Wing: Teal & Sage Modern Studio Pavilion */}
        <rect
          x="292"
          y="118"
          width="118"
          height="154"
          rx="14"
          fill="var(--primary-soft)"
          stroke="var(--primary)"
          strokeWidth="2"
        />
        <rect
          x="312"
          y="140"
          width="34"
          height="42"
          rx="8"
          fill="var(--card)"
          stroke="var(--primary)"
          strokeWidth="1.5"
        />
        <rect
          x="356"
          y="140"
          width="34"
          height="42"
          rx="8"
          fill="var(--marigold-soft)"
          stroke="var(--marigold)"
          strokeWidth="1.5"
        />
        <rect
          x="312"
          y="196"
          width="78"
          height="46"
          rx="10"
          fill="var(--neem-soft)"
          stroke="var(--neem)"
          strokeWidth="1.5"
        />

        {/* Botanical Courtyard Trees & Planters */}
        <g>
          <circle cx="64" cy="222" r="32" fill="var(--neem)" fillOpacity="0.85" />
          <circle cx="44" cy="236" r="22" fill="var(--neem-soft-foreground)" fillOpacity="0.75" />
          <rect x="59" y="242" width="10" height="30" rx="3" fill="var(--ember)" />

          <circle cx="396" cy="232" r="26" fill="var(--neem)" fillOpacity="0.9" />
          <rect x="392" y="250" width="8" height="22" rx="3" fill="var(--ember)" />
        </g>

        {/* Courtyard Terracotta Pathway */}
        <rect x="0" y="270" width="440" height="40" fill="var(--ember)" fillOpacity="0.18" />
        <path d="M154 270 L124 310 L268 310 L238 270 Z" fill="var(--marigold)" fillOpacity="0.3" />

        {/* Floating Verified Shield Medallion */}
        <g transform="translate(26, 28)">
          <rect
            width="64"
            height="64"
            rx="18"
            fill="var(--card)"
            stroke="var(--primary)"
            strokeWidth="2"
          />
          <path
            d="M32 14 L48 21 V32 C48 42.5 41.2 50.8 32 54 C22.8 50.8 16 42.5 16 32 V21 L32 14 Z"
            fill="var(--primary-soft)"
            stroke="var(--primary)"
            strokeWidth="2"
          />
          <path
            d="M25 33 L30 38 L40 27"
            stroke="var(--primary)"
            strokeWidth="2.75"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </g>
      </svg>

      {/* Decorative multi-color architectural ribbon bar */}
      <div className="mt-4 grid grid-cols-4 gap-2">
        <span className="h-2 rounded-full bg-primary/70" />
        <span className="h-2 rounded-full bg-marigold/70" />
        <span className="h-2 rounded-full bg-ember/70" />
        <span className="h-2 rounded-full bg-neem/70" />
      </div>
    </div>
  );
}

/** Decorative corner motif for the 4 "How it works" bento cards. */
export function StepCornerMotif({
  step,
  className,
}: {
  step: "find" | "visit" | "reserve" | "moveIn";
  className?: string;
}) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 120 80"
      fill="none"
      className={cn("pointer-events-none h-14 w-20 shrink-0 opacity-85", className)}
    >
      {step === "find" ? (
        <>
          <circle cx="84" cy="40" r="28" fill="var(--primary)" fillOpacity="0.14" />
          <circle
            cx="84"
            cy="40"
            r="18"
            stroke="var(--primary)"
            strokeWidth="1.75"
            strokeDasharray="4 4"
          />
          <circle cx="84" cy="40" r="6" fill="var(--primary)" />
          <circle cx="42" cy="54" r="10" fill="var(--neem)" fillOpacity="0.22" />
        </>
      ) : step === "visit" ? (
        <>
          <path
            d="M56 72 V36 C56 16 96 16 96 36 V72 Z"
            fill="var(--marigold)"
            fillOpacity="0.18"
            stroke="var(--marigold)"
            strokeWidth="1.75"
          />
          <circle cx="76" cy="36" r="7" fill="var(--ember)" fillOpacity="0.7" />
        </>
      ) : step === "reserve" ? (
        <>
          <rect
            x="48"
            y="16"
            width="54"
            height="48"
            rx="12"
            fill="var(--dusk)"
            fillOpacity="0.15"
            stroke="var(--dusk)"
            strokeWidth="1.75"
          />
          <circle cx="75" cy="40" r="10" fill="var(--primary)" fillOpacity="0.3" />
        </>
      ) : (
        <>
          <circle
            cx="62"
            cy="40"
            r="16"
            fill="var(--ember)"
            fillOpacity="0.18"
            stroke="var(--ember)"
            strokeWidth="2"
          />
          <path
            d="M78 40 H108 M98 40 V50 M106 40 V47"
            stroke="var(--ember)"
            strokeWidth="2.25"
            strokeLinecap="round"
          />
        </>
      )}
    </svg>
  );
}

export { HeroCourtyardArt as HeroCourtyardIllustration };

/** Subtle architectural arch & jali lattice watermark for color-blocked cards and headers. */
export function ArchWatermark({
  tone = "ink",
  className,
}: {
  tone?: "ink" | "ember" | "marigold" | "dusk" | "neem";
  className?: string;
}) {
  const strokeColor =
    tone === "ember"
      ? "var(--ember)"
      : tone === "marigold"
        ? "var(--marigold)"
        : tone === "dusk"
          ? "var(--dusk)"
          : tone === "neem"
            ? "var(--neem)"
            : "var(--primary)";
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 120 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("pointer-events-none select-none", className)}
    >
      <path
        d="M20 116 V56 C20 26 100 26 100 56 V116"
        stroke={strokeColor}
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <path
        d="M34 116 V60 C34 38 86 38 86 60 V116"
        stroke={strokeColor}
        strokeWidth="1.75"
        strokeDasharray="4 4"
      />
      <circle cx="60" cy="24" r="6" fill={strokeColor} />
    </svg>
  );
}

/** Colorful architectural placeholder when a PG card has no uploaded cover photo yet. */
export function ListingPlaceholderArt({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 160 160"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("h-full w-full object-cover", className)}
    >
      <rect width="160" height="160" fill="var(--marigold-soft)" />
      <circle cx="126" cy="34" r="20" fill="var(--marigold)" fillOpacity="0.35" />
      <rect
        x="26"
        y="46"
        width="108"
        height="114"
        rx="10"
        fill="var(--ember-soft)"
        stroke="var(--ember-border)"
        strokeWidth="2"
      />
      <rect x="26" y="46" width="108" height="10" rx="4" fill="var(--ember)" fillOpacity="0.75" />
      <path
        d="M62 160 V110 C62 92 98 92 98 110 V160 Z"
        fill="var(--primary-soft)"
        stroke="var(--primary)"
        strokeWidth="2"
      />
      <rect x="42" y="68" width="20" height="22" rx="5" fill="var(--dusk-soft)" />
      <rect x="98" y="68" width="20" height="22" rx="5" fill="var(--dusk-soft)" />
      <circle cx="24" cy="138" r="18" fill="var(--neem)" fillOpacity="0.8" />
      <circle cx="138" cy="142" r="15" fill="var(--neem)" fillOpacity="0.8" />
    </svg>
  );
}
