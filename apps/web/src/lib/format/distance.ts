/** Distances as people say them: "650 m" to the nearest 10 m, then "1.2 km" (en-IN). */

const metres = new Intl.NumberFormat("en-IN", {
  style: "unit",
  unit: "meter",
  maximumFractionDigits: 0,
});
const kilometres = new Intl.NumberFormat("en-IN", {
  style: "unit",
  unit: "kilometer",
  maximumFractionDigits: 1,
});

export function formatDistance(distanceM: number): string {
  const nearestTen = Math.max(10, Math.round(distanceM / 10) * 10);
  if (nearestTen < 1_000) return metres.format(nearestTen);
  return kilometres.format(Math.round(distanceM / 100) / 10);
}
