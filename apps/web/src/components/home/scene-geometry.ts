/**
 * The shapes of the home page's evening scene: a Delhi street seen from a rooftop, drawn from seeded
 * random numbers once when the module loads, so every visitor gets the same picture and the server
 * ships plain SVG paths. Nothing here is a real building. All layers share a 1600 by 500 drawing.
 */

export const SCENE_WIDTH = 1600;
export const SCENE_HEIGHT = 500;

function seeded(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const whole = (value: number) => Math.round(value);

function box(x: number, y: number, width: number, height: number): string {
  return String.raw`M${whole(x)} ${whole(y)}h${whole(width)}v${whole(height)}h${-whole(width)}z`;
}

/** A water tank on a rooftop: the black drum on every Delhi terrace. */
function tank(x: number, roof: number, width: number): string {
  const height = whole(width * 0.82);
  const top = roof - height - 4;
  return (
    String.raw`M${whole(x)} ${roof - 4}v${-(height - 5)}q0 -5 5 -5h${whole(width) - 10}q5 0 5 5v${height - 5}z` +
    box(x + 3, top + height, 3, 4) +
    box(x + width - 6, top + height, 3, 4)
  );
}

interface Skyline {
  body: string;
  /** Three sets of lit windows, so they can come on at different times. */
  lit: readonly [string, string, string];
}

/** A far, hazy skyline: plain blocks, one dome and two minarets. */
function farSkyline(): string {
  const random = seeded(11);
  const parts: string[] = [];
  let x = -10;
  while (x < SCENE_WIDTH) {
    const width = 36 + random() * 74;
    const height = 70 + random() * 110;
    parts.push(box(x, SCENE_HEIGHT - height, width, height));
    x += width + random() * 10;
  }
  const domeX = 1120;
  const domeBase = SCENE_HEIGHT - 150;
  parts.push(
    box(domeX - 60, domeBase, 120, 150),
    String.raw`M${domeX - 44} ${domeBase}c0 -56 28 -72 44 -86c16 14 44 30 44 86z`,
    box(domeX - 2, domeBase - 104, 4, 20),
    box(domeX - 112, SCENE_HEIGHT - 226, 13, 226),
    box(domeX + 99, SCENE_HEIGHT - 226, 13, 226),
    String.raw`M${domeX - 116} ${SCENE_HEIGHT - 226}l10.5 -22l10.5 22z`,
    String.raw`M${domeX + 95} ${SCENE_HEIGHT - 226}l10.5 -22l10.5 22z`,
  );
  return parts.join("");
}

/** A row of PG blocks, with parapets, stair heads, water tanks and windows. */
function blocks(
  seed: number,
  height: readonly [number, number],
  width: readonly [number, number],
): Skyline {
  const random = seeded(seed);
  const body: string[] = [];
  const lit: [string[], string[], string[]] = [[], [], []];
  let x = -14;
  while (x < SCENE_WIDTH) {
    const blockWidth = width[0] + random() * (width[1] - width[0]);
    const blockHeight = height[0] + random() * (height[1] - height[0]);
    const roof = whole(SCENE_HEIGHT - blockHeight);
    body.push(box(x, roof, blockWidth, blockHeight), box(x - 3, roof - 5, blockWidth + 6, 6));
    if (random() > 0.35) {
      body.push(box(x + 12 + random() * (blockWidth - 56), roof - 30, 32, 28));
    }
    const tanks = random() > 0.5 ? 2 : 1;
    for (let index = 0; index < tanks; index += 1) {
      body.push(tank(x + 8 + random() * (blockWidth - 44), roof - 5, 24 + random() * 8));
    }
    for (let floor = roof + 20; floor < SCENE_HEIGHT - 26; floor += 36) {
      for (let column = x + 14; column < x + blockWidth - 20; column += 27) {
        if (random() < 0.44) {
          lit[Math.floor(random() * 3)]?.push(box(column, floor, 13, 19));
        }
      }
    }
    x += blockWidth + random() * 8;
  }
  return { body: body.join(""), lit: [lit[0].join(""), lit[1].join(""), lit[2].join("")] };
}

/** The elevated metro: deck, T-shaped piers and a station. */
function viaduct(): { body: string; glass: string } {
  const deck = 292;
  const parts = [box(-10, deck, SCENE_WIDTH + 20, 15), box(-10, deck + 15, SCENE_WIDTH + 20, 6)];
  for (let x = 90; x < SCENE_WIDTH; x += 320) {
    parts.push(
      box(x - 34, deck + 21, 68, 13),
      String.raw`M${x - 16} ${deck + 34}h32l-6 ${SCENE_HEIGHT - deck - 34}h-20z`,
    );
  }
  const stationX = 700;
  const stationWidth = 330;
  parts.push(
    String.raw`M${stationX} ${deck}v-54q${stationWidth / 2} -36 ${stationWidth} 0v54z`,
    box(stationX - 22, deck - 4, stationWidth + 44, 6),
  );
  const glass: string[] = [];
  for (let x = stationX + 18; x < stationX + stationWidth - 22; x += 21) {
    glass.push(box(x, deck - 42, 12, 24));
  }
  return { body: parts.join(""), glass: glass.join("") };
}

const COACH_WIDTH = 148;
const COACHES = 6;

/** A train of six coaches, drawn at the left of the drawing and moved by CSS. */
function train(): { body: string; windows: string } {
  const top = 258;
  const body: string[] = [];
  const windows: string[] = [];
  for (let index = 0; index < COACHES; index += 1) {
    const x = index * (COACH_WIDTH + 5);
    body.push(
      String.raw`M${x + 9} ${top}h${COACH_WIDTH - 18}q9 0 9 9v25h${-COACH_WIDTH}v-25q0 -9 9 -9z`,
    );
    for (let pane = x + 14; pane < x + COACH_WIDTH - 22; pane += 25) {
      windows.push(box(pane, top + 8, 18, 11));
    }
  }
  return { body: body.join(""), windows: windows.join("") };
}

function circle(x: number, y: number, radius: number): string {
  const r = whole(radius);
  return String.raw`M${whole(x) - r} ${whole(y)}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0z`;
}

/** A neem tree: a crown of overlapping leaf clumps on a forked trunk. */
function tree(seed: number, x: number, ground: number, size: number): string {
  const random = seeded(seed);
  const parts = [
    String.raw`M${x - size * 0.07} ${ground}l${size * 0.03} ${-size * 0.72}h${size * 0.08}l${size * 0.03} ${size * 0.72}z`,
    String.raw`M${x} ${ground - size * 0.5}l${-size * 0.3} ${-size * 0.34}l${size * 0.05} -3l${size * 0.3} ${size * 0.3}z`,
    String.raw`M${x} ${ground - size * 0.56}l${size * 0.28} ${-size * 0.3}l${-size * 0.04} -4l${-size * 0.27} ${size * 0.27}z`,
  ];
  for (let index = 0; index < 84; index += 1) {
    const angle = random() * Math.PI * 2;
    const distance = Math.sqrt(random());
    // Small clumps, more of them near the crown's edge, so the outline reads as leaves.
    const edge = 0.7 + random() * 0.3;
    parts.push(
      circle(
        x + Math.cos(angle) * distance * edge * size * 0.72,
        ground - size * 0.94 + Math.sin(angle) * distance * edge * size * 0.36,
        size * (0.03 + random() * 0.05),
      ),
    );
  }
  return parts.join("");
}

/** The city's overhead cables, sagging from pole to pole. */
function cables(poles: readonly number[], top: number): string {
  const lines: string[] = [];
  for (const [index, from] of poles.entries()) {
    const to = poles[index + 1];
    if (to === undefined) continue;
    const span = to - from;
    for (let wire = 0; wire < 3; wire += 1) {
      const y = top + wire * 7;
      lines.push(String.raw`M${from} ${y}q${span / 2} ${34 + wire * 7} ${span} 0`);
    }
  }
  return lines.join("");
}

const POLES = [-40, 330, 640, 1240, 1660] as const;
const POLE_TOP = 318;

function nearStreet(): {
  body: string;
  cables: string;
  lamps: readonly (readonly [number, number])[];
} {
  const parts = [tree(3, 90, 500, 300), tree(5, 1510, 500, 340), tree(9, 480, 500, 170)];
  for (const x of POLES) {
    parts.push(
      box(x - 3, POLE_TOP - 6, 6, SCENE_HEIGHT - POLE_TOP + 6),
      box(x - 16, POLE_TOP - 2, 32, 4),
    );
  }
  parts.push(box(0, SCENE_HEIGHT - 20, SCENE_WIDTH, 20));
  return {
    body: parts.join(""),
    cables: cables(POLES, POLE_TOP),
    lamps: [
      [640, POLE_TOP - 10],
      [1240, POLE_TOP - 10],
    ],
  };
}

export const scene = {
  far: farSkyline(),
  back: blocks(23, [120, 225], [80, 150]),
  front: blocks(41, [90, 180], [105, 180]),
  viaduct: viaduct(),
  train: train(),
  near: nearStreet(),
} as const;
