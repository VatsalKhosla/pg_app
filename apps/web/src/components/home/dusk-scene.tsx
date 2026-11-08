import type { ReactNode } from "react";

import { SCENE_HEIGHT, SCENE_WIDTH, scene } from "./scene-geometry";

const viewBox = String.raw`0 0 ${SCENE_WIDTH} ${SCENE_HEIGHT}`;

function Layer({
  depth,
  className,
  children,
}: {
  depth: number;
  className?: string;
  children: ReactNode;
}) {
  return (
    <svg
      viewBox={viewBox}
      preserveAspectRatio="xMidYMax slice"
      className={className === undefined ? "dusk-layer" : `dusk-layer ${className}`}
      style={{ "--depth": depth }}
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

function Kite({ x, y, size, tone }: { x: number; y: number; size: number; tone: string }) {
  const half = size / 2;
  return (
    <g>
      <path
        d={String.raw`M${x} ${y - size}L${x + half} ${y}L${x} ${y + size * 0.7}L${x - half} ${y}Z`}
        fill={tone}
      />
      <path
        d={String.raw`M${x - half} ${y}H${x + half}M${x} ${y - size}V${y + size * 0.7}`}
        stroke="var(--scene-night)"
        strokeOpacity="0.35"
        strokeWidth="1"
      />
      <path
        d={String.raw`M${x} ${y + size * 0.7}q-8 16 2 30t-3 28`}
        fill="none"
        stroke={tone}
        strokeWidth="1.6"
      />
    </g>
  );
}

/**
 * The home page's evening: Delhi from a rooftop as the sun goes down, drawn as flat layers set at
 * different depths. Scrolling takes the sun below the horizon and turns the windows on, in CSS
 * alone; the pointer moves the layers against each other on desktops (HeroParallax). It's an
 * illustration, not a place we list, and under reduced motion it stays still.
 */
export function DuskScene() {
  return (
    <div className="dusk-scene" aria-hidden="true">
      <div className="dusk-sky" />
      <div className="dusk-sun" style={{ "--depth": 3 }} />
      <div className="dusk-dark" />
      <div className="dusk-stars" />

      <Layer depth={15} className="dusk-kites">
        <Kite x={1215} y={78} size={34} tone="var(--scene-kite-a)" />
        <Kite x={1395} y={150} size={24} tone="var(--scene-kite-b)" />
        <Kite x={905} y={132} size={20} tone="var(--scene-kite-c)" />
      </Layer>
      <Layer depth={5} className="dusk-drift">
        <path d={scene.far} fill="var(--scene-far)" />
      </Layer>
      <Layer depth={9} className="dusk-drift">
        <path d={scene.back.body} fill="var(--scene-back)" />
        <path d={scene.back.lit[0]} className="dusk-window" />
      </Layer>
      <Layer depth={9} className="dusk-lights-early">
        <path d={scene.back.lit[1]} className="dusk-window" />
      </Layer>
      <Layer depth={13} className="dusk-drift">
        <path d={scene.front.body} fill="var(--scene-front)" />
        <path d={scene.front.lit[0]} className="dusk-window" />
      </Layer>
      <Layer depth={13} className="dusk-lights-early">
        <path d={scene.front.lit[1]} className="dusk-window" />
      </Layer>
      <Layer depth={13} className="dusk-lights-late">
        <path d={scene.front.lit[2]} className="dusk-window" />
      </Layer>
      <Layer depth={18} className="dusk-drift">
        <path d={scene.viaduct.body} fill="var(--scene-metro)" />
        <path d={scene.viaduct.glass} className="dusk-window" />
      </Layer>
      <Layer depth={18} className="dusk-train">
        <path d={scene.train.body} fill="var(--scene-train)" />
        <path d={scene.train.windows} fill="var(--scene-lit)" />
      </Layer>
      <Layer depth={28} className="dusk-drift">
        <path d={scene.near.cables} fill="none" stroke="var(--scene-near)" strokeWidth="1.5" />
        <path d={scene.near.body} fill="var(--scene-near)" />
        {scene.near.lamps.map(([x, y]) => (
          <g key={x}>
            <circle cx={x} cy={y} r="22" fill="var(--scene-lit)" opacity="0.18" />
            <circle cx={x} cy={y} r="5" fill="var(--scene-lit)" />
          </g>
        ))}
      </Layer>
    </div>
  );
}
