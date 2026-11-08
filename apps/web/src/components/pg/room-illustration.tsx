import type { Schemas } from "@pg-platform/api-client";

type Occupancy = Schemas["PublicCategory"]["occupancy"];

/** One grid unit on the screen. The room is drawn in isometric projection, from above and in front. */
const UNIT = 22;
const ORIGIN_X = 118;
const ORIGIN_Y = 62;
const COS = 0.866;
const SIN = 0.5;
const ROOM_X = 5.4;
const ROOM_Y = 4.8;
const WALL = 2.5;

type Point = readonly [number, number, number];

function iso([x, y, z]: Point): string {
  const screenX = ORIGIN_X + (x - y) * COS * UNIT;
  const screenY = ORIGIN_Y + (x + y) * SIN * UNIT - z * UNIT;
  return `${screenX.toFixed(1)},${screenY.toFixed(1)}`;
}

function Face({ points, fill }: { points: readonly Point[]; fill: string }) {
  return <polygon points={points.map(iso).join(" ")} fill={fill} />;
}

interface BoxProps {
  at: Point;
  size: Point;
  top: string;
  left: string;
  right: string;
}

/** A box's three visible faces. */
function Box({ at: [x, y, z], size: [dx, dy, dz], top, left, right }: BoxProps) {
  const up = z + dz;
  return (
    <g>
      <Face
        points={[
          [x, y + dy, z],
          [x + dx, y + dy, z],
          [x + dx, y + dy, up],
          [x, y + dy, up],
        ]}
        fill={left}
      />
      <Face
        points={[
          [x + dx, y, z],
          [x + dx, y + dy, z],
          [x + dx, y + dy, up],
          [x + dx, y, up],
        ]}
        fill={right}
      />
      <Face
        points={[
          [x, y, up],
          [x + dx, y, up],
          [x + dx, y + dy, up],
          [x, y + dy, up],
        ]}
        fill={top}
      />
    </g>
  );
}

const BED_X = 1.15;
const BED_Y = 2.1;

function Bed({ x, y }: { x: number; y: number }) {
  const pad = 0.14;
  return (
    <g>
      {/* The shadow it casts on the floor. */}
      <Face
        points={[
          [x - pad, y - pad, 0],
          [x + BED_X + pad, y - pad, 0],
          [x + BED_X + pad, y + BED_Y + pad, 0],
          [x - pad, y + BED_Y + pad, 0],
        ]}
        fill="var(--iso-shadow)"
      />
      <Box
        at={[x, y, 0]}
        size={[BED_X, 0.14, 1.05]}
        top="var(--iso-frame-top)"
        left="var(--iso-frame-left)"
        right="var(--iso-frame-right)"
      />
      <Box
        at={[x, y + 0.14, 0]}
        size={[BED_X, BED_Y - 0.14, 0.34]}
        top="var(--iso-frame-top)"
        left="var(--iso-frame-left)"
        right="var(--iso-frame-right)"
      />
      <Box
        at={[x + 0.04, y + 0.16, 0.34]}
        size={[BED_X - 0.08, BED_Y - 0.2, 0.22]}
        top="var(--iso-sheet-top)"
        left="var(--iso-sheet-left)"
        right="var(--iso-sheet-right)"
      />
      <Box
        at={[x + 0.2, y + 0.24, 0.56]}
        size={[BED_X - 0.4, 0.4, 0.12]}
        top="var(--iso-sheet-top)"
        left="var(--iso-sheet-left)"
        right="var(--iso-sheet-right)"
      />
      <Box
        at={[x + 0.02, y + 0.92, 0.34]}
        size={[BED_X - 0.04, BED_Y - 0.94, 0.26]}
        top="var(--iso-pillow)"
        left="var(--iso-blanket-left)"
        right="var(--iso-blanket-right)"
      />
    </g>
  );
}

/** Where the beds stand, back of the room first so nearer ones are drawn over them. */
const BEDS: Record<Occupancy, readonly (readonly [number, number])[]> = {
  single: [[0.2, 0.2]],
  double: [
    [0.2, 0.2],
    [4.05, 0.2],
  ],
  triple: [
    [0.2, 0.2],
    [2.12, 0.2],
    [4.05, 0.2],
  ],
  quad: [
    [0.2, 0.2],
    [4.05, 0.2],
    [0.2, 2.55],
    [4.05, 2.55],
  ],
};

/**
 * How a room type's beds sit, drawn from its own fields: how many beds, and whether it has AC, an
 * attached bathroom or a balcony. It's a labelled illustration of the layout, never a picture of
 * this PG's room, and it's plain SVG from the server, with no script.
 */
export function RoomIllustration({
  occupancy,
  ac,
  attachedBath,
  balcony,
  caption,
}: {
  occupancy: Occupancy;
  ac: boolean;
  attachedBath: boolean;
  balcony: boolean;
  caption: string;
}) {
  return (
    <figure className="iso-room m-0 max-w-60">
      <svg
        viewBox="0 0 236 196"
        className="block h-auto w-full"
        aria-hidden="true"
        focusable="false"
        data-beds={BEDS[occupancy].length}
      >
        <Face
          points={[
            [0, 0, 0],
            [ROOM_X, 0, 0],
            [ROOM_X, ROOM_Y, 0],
            [0, ROOM_Y, 0],
          ]}
          fill="var(--iso-floor)"
        />
        <Face
          points={[
            [0, 0, 0],
            [ROOM_X, 0, 0],
            [ROOM_X, 0, WALL],
            [0, 0, WALL],
          ]}
          fill="var(--iso-wall-a)"
        />
        <Face
          points={[
            [0, 0, 0],
            [0, ROOM_Y, 0],
            [0, ROOM_Y, WALL],
            [0, 0, WALL],
          ]}
          fill="var(--iso-wall-b)"
        />
        {attachedBath ? (
          <g data-feature="bath">
            <Face
              points={[
                [0, 3.3, 0],
                [0, 4.4, 0],
                [0, 4.4, 2],
                [0, 3.3, 2],
              ]}
              fill="var(--iso-door)"
            />
            <Face
              points={[
                [0, 4.15, 0.95],
                [0, 4.27, 0.95],
                [0, 4.27, 1.07],
                [0, 4.15, 1.07],
              ]}
              fill="var(--iso-accent)"
            />
          </g>
        ) : null}
        {balcony ? (
          <g data-feature="balcony">
            <Face
              points={[
                [2, 0, 0],
                [3.4, 0, 0],
                [3.4, 0, 2.05],
                [2, 0, 2.05],
              ]}
              fill="var(--iso-glass)"
            />
            <Face
              points={[
                [2.68, 0, 0],
                [2.72, 0, 0],
                [2.72, 0, 2.05],
                [2.68, 0, 2.05],
              ]}
              fill="var(--iso-frame-top)"
            />
          </g>
        ) : null}
        {ac ? (
          <g data-feature="ac">
            <Box
              at={[1.65, 0, 2.02]}
              size={[1.8, 0.24, 0.34]}
              top="var(--iso-ac-light)"
              left="var(--iso-ac-mid)"
              right="var(--iso-ac-dark)"
            />
          </g>
        ) : null}
        {BEDS[occupancy].map(([x, y]) => (
          <Bed key={`${String(x)}-${String(y)}`} x={x} y={y} />
        ))}
      </svg>
      <figcaption className="mt-1 text-xs leading-snug text-muted-foreground">{caption}</figcaption>
    </figure>
  );
}
