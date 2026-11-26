"""Make the site's logo files from the founders' logo (2026-11-26): a teal house in a gold ring, on
white. Run it again when they send a new one:

    uv run --directory apps/api python ../../scripts/brand-logo.py [path/to/their-logo.jpg]

With no path, it reads apps/web/src/assets/brand/logo-original.jpg (copy theirs there first). It
finds the ring by its gold, cuts the logo out along the ring's outer edge (transparent outside,
the ring's white face kept), and writes, in apps/web/src/assets/brand:
- logo.png: the cut-out, at the original's own resolution (never enlarged);
- logo-mark.webp: 96 px, for the header and footer (36 to 40 px wide, on screens up to 2.4x);
and apps/web/src/components/brand/logo-data.ts, the cut-out as a data URL for next/og's app icons
and link pictures, which need the image itself rather than its address.
"""

import base64
import io
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "apps/web/src/assets/brand"
DATA_MODULE = ROOT / "apps/web/src/components/brand/logo-data.ts"
MARK_SIZE = 96
MARK_QUALITY = 90
# How the ring's gold differs from the white around it and the grey of its shadow.
GOLD_RED_OVER_BLUE = 35
GOLD_MIN_RED = 120
# Rays out from the centre, and the share of them whose last gold pixel bounds the ring: a high
# percentile, as bright highlights on the ring end some rays early.
RAYS = 720
EDGE_PERCENTILE = 0.9
SUPERSAMPLE = 8


def _is_gold(pixel: tuple[int, int, int]) -> bool:
    red, _green, blue = pixel
    return red - blue > GOLD_RED_OVER_BLUE and red > GOLD_MIN_RED


def _edge_points(
    image: Image.Image, centre: tuple[float, float], reach: range
) -> list[tuple[float, float]]:
    """Where the gold ends along each ray out from the centre."""
    pixels = image.load()
    width, height = image.size
    points = []
    for ray in range(RAYS):
        angle = 2 * math.pi * ray / RAYS
        last = None
        for step in reach:
            x = centre[0] + step * math.cos(angle)
            y = centre[1] + step * math.sin(angle)
            if not (0 <= round(x) < width and 0 <= round(y) < height):
                break
            if _is_gold(pixels[round(x), round(y)]):
                last = (x, y)
        if last is not None:
            points.append(last)
    return points


def _fit_circle(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """The least-squares circle through the points (Kåsa's method): centre and radius."""
    n = len(points)
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    sxx = sum(x * x for x, _ in points)
    syy = sum(y * y for _, y in points)
    sxy = sum(x * y for x, y in points)
    sz = sum(x * x + y * y for x, y in points)
    sxz = sum(x * (x * x + y * y) for x, y in points)
    syz = sum(y * (x * x + y * y) for x, y in points)
    rows = [[sxx, sxy, sx, sxz], [sxy, syy, sy, syz], [sx, sy, float(n), sz]]
    for i in range(3):
        pivot = max(range(i, 3), key=lambda r: abs(rows[r][i]))
        rows[i], rows[pivot] = rows[pivot], rows[i]
        for r in range(3):
            if r != i:
                factor = rows[r][i] / rows[i][i]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[i], strict=True)]
    a, b, c = (rows[i][3] / rows[i][i] for i in range(3))
    cx, cy = a / 2, b / 2
    return cx, cy, math.sqrt(c + cx * cx + cy * cy)


def _ring(image: Image.Image) -> tuple[float, float, float]:
    """The ring's centre and outer radius."""
    width, height = image.size
    reach = range(min(width, height) // 4, max(width, height))
    cx, cy, _ = _fit_circle(_edge_points(image, (width / 2, height / 2), reach))
    distances = sorted(math.hypot(x - cx, y - cy) for x, y in _edge_points(image, (cx, cy), reach))
    return cx, cy, distances[int(len(distances) * EDGE_PERCENTILE)] + 1.0


def _cut_out(image: Image.Image) -> Image.Image:
    cx, cy, radius = _ring(image)
    side = math.ceil(2 * radius) + 2
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(image, (round(side / 2 - cx), round(side / 2 - cy)))
    big = side * SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    edge = (side / 2 - radius) * SUPERSAMPLE
    ImageDraw.Draw(mask).ellipse([edge, edge, big - edge, big - edge], fill=255)
    cut = canvas.convert("RGBA")
    cut.putalpha(mask.resize((side, side), Image.Resampling.LANCZOS))
    return cut


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ASSETS / "logo-original.jpg"
    logo = _cut_out(Image.open(source).convert("RGB"))
    full = _png(logo)
    (ASSETS / "logo.png").write_bytes(full)
    mark = logo.resize((MARK_SIZE, MARK_SIZE), Image.Resampling.LANCZOS)
    mark.save(ASSETS / "logo-mark.webp", format="WEBP", quality=MARK_QUALITY, method=6)
    DATA_MODULE.write_text(
        "// Made by scripts/brand-logo.py from src/assets/brand/logo-original.jpg: don't edit.\n"
        "\n"
        "/** The founders' logo as a PNG data URL, for next/og's ImageResponse, which needs the image\n"
        " * itself: the app icons and the pictures social sites show for a link. */\n"
        f'export const LOGO_DATA_URL =\n  "data:image/png;base64,{base64.b64encode(full).decode()}";\n'
        "\n"
        "/** Its size in pixels: square. */\n"
        f"export const LOGO_SIZE = {logo.width};\n",
        encoding="utf-8",
    )
    print(f"logo.png {logo.width} px ({len(full) // 1024} KB), logo-mark.webp {MARK_SIZE} px")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
