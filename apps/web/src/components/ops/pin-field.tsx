"use client";

import { LocateFixed } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import type { UseFormRegisterReturn } from "react-hook-form";

import { type LatLng, NCR_BOUNDS, roundCoordinate } from "@/components/map/map-provider";
import { hasMap, PinPicker } from "@/components/map/pin-picker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { Field } from "@/components/ui/fields";

/** A typed latitude or longitude, or null when it isn't a number in decimal degrees. */
export function parseCoordinate(text: string): number | null {
  const trimmed = text.trim();
  return /^-?\d{1,3}(?:\.\d{1,12})?$/u.test(trimmed) ? Number(trimmed) : null;
}

export function formatCoordinate(value: number): string {
  return roundCoordinate(value).toFixed(6);
}

/** The pin the two fields describe, if both are numbers inside NCR. */
export function pinOf(lat: string, lng: string): LatLng | null {
  const latitude = parseCoordinate(lat);
  const longitude = parseCoordinate(lng);
  if (latitude === null || longitude === null) return null;
  const inside =
    NCR_BOUNDS.south <= latitude &&
    latitude <= NCR_BOUNDS.north &&
    NCR_BOUNDS.west <= longitude &&
    longitude <= NCR_BOUNDS.east;
  return inside ? { lat: latitude, lng: longitude } : null;
}

type Locating =
  | { state: "idle" }
  | { state: "locating" }
  | { state: "found"; accuracy: number }
  | { state: "failed" };

/**
 * Where the PG is: the map (when there is one), the phone's location, and the coordinates
 * themselves, which the form keeps. All three stay in step.
 */
export function PinField({
  id,
  lat,
  lng,
  pin,
  onPin,
  center,
  errors,
}: {
  id: string;
  lat: UseFormRegisterReturn;
  lng: UseFormRegisterReturn;
  pin: LatLng | null;
  onPin: (pin: LatLng) => void;
  center: LatLng | undefined;
  errors: { lat?: string | undefined; lng?: string | undefined };
}) {
  const t = useTranslations("Ops.pin");
  const [locating, setLocating] = useState<Locating>({ state: "idle" });

  function locate() {
    if (!("geolocation" in navigator)) {
      setLocating({ state: "failed" });
      return;
    }
    setLocating({ state: "locating" });
    navigator.geolocation.getCurrentPosition(
      (position) => {
        onPin({
          lat: roundCoordinate(position.coords.latitude),
          lng: roundCoordinate(position.coords.longitude),
        });
        setLocating({ state: "found", accuracy: Math.round(position.coords.accuracy) });
      },
      () => {
        setLocating({ state: "failed" });
      },
      { enableHighAccuracy: true, timeout: 20_000, maximumAge: 0 },
    );
  }

  return (
    <fieldset className="space-y-4">
      <legend className="text-sm font-medium">{t("legend")}</legend>
      <p className="text-sm text-muted-foreground">{hasMap ? t("hint") : t("hintNoMap")}</p>
      <PinPicker
        value={pin}
        onChange={onPin}
        center={center}
        text={{
          map: t("map"),
          pin: t("pin"),
          zoomIn: t("zoomIn"),
          zoomOut: t("zoomOut"),
          credits: t("credits"),
          twoFingers: t("twoFingers"),
          ctrlScroll: t("ctrlScroll"),
          cmdScroll: t("cmdScroll"),
          failed: t("mapFailed"),
        }}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="outline"
          size="lg"
          disabled={locating.state === "locating"}
          onClick={locate}
        >
          <LocateFixed aria-hidden />
          {locating.state === "locating" ? t("locating") : t("useLocation")}
        </Button>
        <p role="status" className="text-sm text-muted-foreground">
          {locating.state === "found"
            ? t("accuracy", { metres: locating.accuracy })
            : locating.state === "failed"
              ? t("locationFailed")
              : ""}
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id={`${id}-lat`} label={t("lat")} error={errors.lat}>
          {(control) => <Input {...control} inputMode="decimal" autoComplete="off" {...lat} />}
        </Field>
        <Field id={`${id}-lng`} label={t("lng")} error={errors.lng}>
          {(control) => <Input {...control} inputMode="decimal" autoComplete="off" {...lng} />}
        </Field>
      </div>
    </fieldset>
  );
}
