import { prefersStillness } from "../gestures";
import type { LatLng } from "../map-provider";
import { between, ease, flight, type Size, type View } from "./geometry";

/** A camera to move to: any of the middle, zoom, tilt and heading. */
export interface Shot {
  center?: LatLng;
  zoom?: number;
  tilt?: number;
  heading?: number;
}

// Flights shorter than this look like a twitch, and longer ones like a wait.
const FLIGHT_MS = { min: 400, max: 2_000 };

/**
 * The Google map's moves, glided frame by frame with moveCamera (Google animates only short pans
 * itself), so going to a campus, opening a cluster or zooming eases and flies as on MapLibre
 * (ADR 0069). Anyone who asks for less motion gets every move at once. A raster map, Google's
 * fallback where WebGL can't run, has whole zoom levels only, so it jumps too.
 */
export class Camera {
  private frame: number | null = null;

  constructor(
    private readonly map: google.maps.Map,
    private readonly vector: () => boolean,
  ) {}

  /** Whether a glide is under way: its frames' idle events aren't the map coming to rest. */
  get moving(): boolean {
    return this.frame !== null;
  }

  /** Stops a glide where it is, as when the person takes hold of the map. */
  stop(): void {
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.frame = null;
  }

  jump(shot: Shot): void {
    this.stop();
    if (this.vector()) {
      this.map.moveCamera(shot);
      return;
    }
    // A raster map takes neither tilt nor heading, and only whole zoom levels.
    const { center, zoom } = shot;
    this.map.moveCamera({
      ...(center === undefined ? {} : { center }),
      ...(zoom === undefined ? {} : { zoom: Math.round(zoom) }),
    });
  }

  /** Eases the middle and zoom (and tilt and heading) there together over `ms`. */
  ease(shot: Shot, ms: number): void {
    if (prefersStillness() || !this.vector()) {
      this.jump(shot);
      return;
    }
    const from = this.view();
    const fromTilt = this.map.getTilt() ?? 0;
    const fromHeading = this.map.getHeading() ?? 0;
    const to: View = { center: shot.center ?? from.center, zoom: shot.zoom ?? from.zoom };
    this.run(ms, (k) => {
      const view = between(from, to, k);
      return {
        center: view.center,
        zoom: view.zoom,
        ...(shot.tilt === undefined ? {} : { tilt: fromTilt + (shot.tilt - fromTilt) * k }),
        ...(shot.heading === undefined
          ? {}
          : { heading: fromHeading + (shot.heading - fromHeading) * k }),
      };
    });
  }

  /** Flies there, out and back in, as MapLibre's flyTo: for places far from the current view. */
  fly(to: View, size: Size): void {
    if (prefersStillness() || !this.vector()) {
      this.jump(to);
      return;
    }
    const path = flight(this.view(), to, size);
    const ms = Math.min(FLIGHT_MS.max, Math.max(FLIGHT_MS.min, path.ms));
    this.run(ms, (k) => path.at(k));
  }

  private view(): View {
    const center = this.map.getCenter();
    return {
      center: center === undefined ? { lat: 0, lng: 0 } : { lat: center.lat(), lng: center.lng() },
      zoom: this.map.getZoom() ?? 0,
    };
  }

  private run(ms: number, at: (k: number) => google.maps.CameraOptions): void {
    this.stop();
    const started = performance.now();
    const step = (now: number) => {
      const k = Math.min(1, (now - started) / ms);
      this.frame = k < 1 ? requestAnimationFrame(step) : null;
      this.map.moveCamera(at(ease(k)));
    };
    this.frame = requestAnimationFrame(step);
  }
}
