import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const KEY = "fake-browser-key-for-unit-tests-0001";

async function loadChoice() {
  vi.resetModules();
  return import("@/components/map/choice");
}

describe("chooseMap", () => {
  it("prefers Google's map, falls back to MapLibre's tiles, and says when there's neither", async () => {
    const { chooseMap } = await loadChoice();

    expect(chooseMap({ google: true, tiles: true }, false)).toBe("google");
    expect(chooseMap({ google: true, tiles: false }, false)).toBe("google");
    expect(chooseMap({ google: false, tiles: true }, false)).toBe("maplibre");
    expect(chooseMap({ google: false, tiles: false }, false)).toBe("none");
    // Google failed in this visit: the tiles if there are any, else the map says it couldn't load.
    expect(chooseMap({ google: true, tiles: true }, true)).toBe("maplibre");
    expect(chooseMap({ google: true, tiles: false }, true)).toBe("failed");
  });
});

describe("useMapChoice", () => {
  it("keeps MapLibre exactly as it was when no Google key is set", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local");
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY", "");
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID", "");
    const { hasAnyMap, useMapChoice } = await loadChoice();

    expect(hasAnyMap).toBe(true);
    expect(renderHook(() => useMapChoice()).result.current).toBe("maplibre");
  });

  it("uses Google's map once both settings are there, and MapLibre's after it fails", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "staging");
    vi.stubEnv("NEXT_PUBLIC_MAP_TILES_URL", "https://tiles.example.test/{z}/{x}/{y}.png");
    vi.stubEnv("NEXT_PUBLIC_MAP_TILES_ATTRIBUTION", "© Example");
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY", KEY);
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID", "8e0a97af9386fef");
    const { reportGoogleMapsFailure, useMapChoice } = await loadChoice();

    const { result } = renderHook(() => useMapChoice());
    expect(result.current).toBe("google");

    act(() => {
      reportGoogleMapsFailure();
    });
    expect(result.current).toBe("maplibre");
  });

  it("has no map on a deployed site with neither Google nor tiles", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_MAP_TILES_URL", "");
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY", "");
    vi.stubEnv("NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID", "");
    const { hasAnyMap, useMapChoice } = await loadChoice();

    expect(hasAnyMap).toBe(false);
    expect(renderHook(() => useMapChoice()).result.current).toBe("none");
  });
});
