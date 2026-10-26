"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ImagePlus, LocateFixed, Trash } from "lucide-react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { SOCIETY_PERMISSIONS } from "@/components/ops/choices";
import { Checkbox, Choices, Field, FormOutcome, Textarea } from "@/components/ops/fields";
import { useOpsProblem } from "@/components/ops/problems";
import { useRefresh } from "@/components/ops/use-refresh";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { z } from "@/lib/forms/zod";
import { upload } from "@/lib/media/client";
import { submitReport, type Visit } from "@/lib/ops/client";

import {
  ANSWERS,
  CONDITIONS,
  CRACKS,
  type Fix,
  LICENCE_NUMBER_MAX,
  MAX_PHOTOS,
  MOST_EXITS,
  NOTES_MAX,
  OLDEST_BUILDING_YEARS,
  reportBody,
  RESULTS,
  type ReportValues,
  WOMEN_SAFETY,
  wholeNumber,
} from "./report-values";

/** What the API takes for a verification photo (apps/api/src/app/modules/media/domain/assets.py). */
const ACCEPT = "image/jpeg,image/png,image/webp";

interface Photo {
  id: string;
  thumbnail: string | undefined;
}

type Upload =
  | { key: string; name: string; state: "uploading" | "processing" }
  | {
      key: string;
      name: string;
      state: "failed";
      reason: string;
    };

function reportSchema(t: ReturnType<typeof useTranslations<"Field.report">>, choose: string) {
  const answer = z.enum(ANSWERS, { error: choose });
  return (
    z
      .object({
        age: z
          .string()
          .refine(
            (text) => text.trim() === "" || wholeNumber(text, 0, OLDEST_BUILDING_YEARS) !== null,
            t("ageInvalid", { oldest: OLDEST_BUILDING_YEARS }),
          ),
        condition: z.enum(CONDITIONS, { error: choose }),
        cracks: z.enum(CRACKS, { error: choose }),
        exits: z
          .string()
          .refine(
            (text) => wholeNumber(text, 0, MOST_EXITS) !== null,
            t("exitsInvalid", { most: MOST_EXITS }),
          ),
        fireExtinguishers: answer,
        cctv: answer,
        warden: answer,
        womenSafety: z.array(z.enum(WOMEN_SAFETY)),
        licenceNumber: z.string().trim().max(LICENCE_NUMBER_MAX, t("tooLong")),
        societyPermission: z.enum(SOCIETY_PERMISSIONS, { error: choose }),
        authorityNotice: answer,
        result: z.enum(RESULTS, { error: choose }),
        notes: z.string().max(NOTES_MAX, t("tooLong")),
        movePin: z.boolean(),
      })
      // The API's rules (ADR 0024), checked here first so the agent hears at once.
      .refine((values) => values.authorityNotice !== "yes" || values.result !== "passed", {
        message: t("noticeCantPass"),
        path: ["result"],
      })
      .refine((values) => values.result !== "failed" || values.notes.trim() !== "", {
        message: t("notesRequired"),
        path: ["notes"],
      }) satisfies z.ZodType<ReportValues, ReportValues>
  );
}

/**
 * The agent's report from the building: every answer, their location (recorded on the spot), the
 * photos, and the result. The API checks the rules that decide it (ADR 0024) and says what's
 * wrong if anything is.
 */
export function ReportForm({ visit }: { visit: Visit }) {
  const t = useTranslations("Field.report");
  const tOps = useTranslations("Ops");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [fix, setFix] = useState<Fix | null>(null);
  const [locating, setLocating] = useState<"idle" | "locating" | "failed">("idle");
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [missing, setMissing] = useState<{ fix: boolean; photos: boolean }>({
    fix: false,
    photos: false,
  });
  const [failure, setFailure] = useState<string | null>(null);
  const form = useForm<ReportValues>({
    resolver: zodResolver(reportSchema(t, tOps("validation.choose"))),
    defaultValues: {
      age: "",
      exits: "",
      womenSafety: [],
      licenceNumber: "",
      notes: "",
      movePin: false,
    },
  });
  const { errors, isSubmitting } = form.formState;
  const yesNo = ANSWERS.map((value) => ({ value, label: t(value) }));

  function locate() {
    if (!("geolocation" in navigator)) {
      setLocating("failed");
      return;
    }
    setLocating("locating");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setFix({
          position: { lat: position.coords.latitude, lng: position.coords.longitude },
          accuracyM: position.coords.accuracy,
        });
        setMissing((current) => ({ ...current, fix: false }));
        setLocating("idle");
      },
      () => {
        setLocating("failed");
      },
      { enableHighAccuracy: true, timeout: 20_000, maximumAge: 0 },
    );
  }

  function track(key: string, next: Upload | null) {
    setUploads((current) => {
      const others = current.filter((item) => item.key !== key);
      return next === null ? others : [...others, next];
    });
  }

  async function add(file: File) {
    const key = crypto.randomUUID();
    track(key, { key, name: file.name, state: "uploading" });
    try {
      const ready = await upload("verification_photo", file, () => {
        track(key, { key, name: file.name, state: "processing" });
      });
      if (ready?.status !== "ready") {
        const reason = ready === null ? t("tooSlow") : (ready.rejectionReason ?? "");
        track(key, { key, name: file.name, state: "failed", reason });
        return;
      }
      const thumbnail = ready.renditions.find((rendition) => rendition.name === "thumb")?.url;
      setPhotos((current) => [...current, { id: ready.id, thumbnail }]);
      setMissing((current) => ({ ...current, photos: false }));
      track(key, null);
    } catch (error) {
      track(key, { key, name: file.name, state: "failed", reason: problem(error) });
    }
  }

  async function submit(values: ReportValues) {
    setFailure(null);
    if (fix === null || photos.length === 0) {
      setMissing({ fix: fix === null, photos: photos.length === 0 });
      return;
    }
    try {
      await submitReport(
        visit.id,
        reportBody(
          values,
          fix,
          photos.map((photo) => photo.id),
        ),
      );
      refresh();
    } catch (error) {
      setFailure(problem(error));
    }
  }

  return (
    <form
      noValidate
      className="space-y-8"
      onSubmit={(event) => {
        void form.handleSubmit(submit)(event);
      }}
    >
      <p className="text-sm text-muted-foreground">{t("intro")}</p>

      <fieldset className="space-y-3">
        <legend className="text-sm font-medium">{t("position")}</legend>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="outline"
            size="lg"
            disabled={locating === "locating"}
            onClick={locate}
          >
            <LocateFixed aria-hidden />
            {locating === "locating" ? t("locating") : t("useLocation")}
          </Button>
          <p role="status" className="text-sm text-muted-foreground">
            {fix !== null
              ? t("located", { metres: Math.round(fix.accuracyM) })
              : locating === "failed"
                ? t("locationFailed")
                : ""}
          </p>
        </div>
        {missing.fix ? (
          <p role="alert" className="text-sm text-destructive">
            {t("positionRequired")}
          </p>
        ) : null}
        <Checkbox label={t("movePin")} {...form.register("movePin")} />
      </fieldset>

      <div className="grid gap-6 sm:grid-cols-2">
        <Field id={`${id}-age`} label={t("age")} error={errors.age?.message}>
          {(control) => (
            <Input {...control} inputMode="numeric" autoComplete="off" {...form.register("age")} />
          )}
        </Field>
        <Field id={`${id}-exits`} label={t("exits")} error={errors.exits?.message}>
          {(control) => (
            <Input
              {...control}
              inputMode="numeric"
              autoComplete="off"
              {...form.register("exits")}
            />
          )}
        </Field>
      </div>
      <Choices
        id={`${id}-condition`}
        legend={t("condition")}
        options={CONDITIONS.map((value) => ({ value, label: t(`conditions.${value}`) }))}
        registration={form.register("condition")}
        error={errors.condition?.message}
        columns={3}
      />
      <Choices
        id={`${id}-cracks`}
        legend={t("cracks")}
        options={CRACKS.map((value) => ({ value, label: t(`crackOptions.${value}`) }))}
        registration={form.register("cracks")}
        error={errors.cracks?.message}
        columns={3}
      />
      <Choices
        id={`${id}-extinguishers`}
        legend={t("extinguishers")}
        options={yesNo}
        registration={form.register("fireExtinguishers")}
        error={errors.fireExtinguishers?.message}
      />
      <Choices
        id={`${id}-cctv`}
        legend={t("cctv")}
        options={yesNo}
        registration={form.register("cctv")}
        error={errors.cctv?.message}
      />
      <Choices
        id={`${id}-warden`}
        legend={t("warden")}
        options={yesNo}
        registration={form.register("warden")}
        error={errors.warden?.message}
      />
      <fieldset className="space-y-1">
        <legend className="text-sm font-medium">{t("womenSafety")}</legend>
        <div className="grid gap-x-6 sm:grid-cols-2">
          {WOMEN_SAFETY.map((value) => (
            <Checkbox
              key={value}
              label={t(`womenSafetyOptions.${value}`)}
              value={value}
              {...form.register("womenSafety")}
            />
          ))}
        </div>
      </fieldset>
      <Field id={`${id}-licence`} label={t("licenceNumber")} error={errors.licenceNumber?.message}>
        {(control) => <Input {...control} autoComplete="off" {...form.register("licenceNumber")} />}
      </Field>
      <Choices
        id={`${id}-society`}
        legend={t("society")}
        options={SOCIETY_PERMISSIONS.map((value) => ({
          value,
          label: tOps(`society.${value}`),
        }))}
        registration={form.register("societyPermission")}
        error={errors.societyPermission?.message}
        columns={3}
      />
      <Choices
        id={`${id}-notice`}
        legend={t("authorityNotice")}
        options={yesNo}
        registration={form.register("authorityNotice")}
        error={errors.authorityNotice?.message}
      />

      <fieldset className="space-y-3">
        <legend className="text-sm font-medium">{t("photos")}</legend>
        <p className="text-sm text-muted-foreground">{t("photosHint")}</p>
        {photos.length === 0 ? null : (
          <ol className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {photos.map((photo, index) => (
              <li key={photo.id} className="space-y-1">
                <div className="relative aspect-square overflow-hidden rounded bg-muted">
                  {photo.thumbnail === undefined ? null : (
                    <Image
                      src={photo.thumbnail}
                      alt={t("photo", { number: index + 1 })}
                      fill
                      unoptimized
                      sizes="160px"
                      className="object-cover"
                    />
                  )}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setPhotos((current) => current.filter((other) => other.id !== photo.id));
                  }}
                >
                  <Trash aria-hidden />
                  {t("removePhoto", { number: index + 1 })}
                </Button>
              </li>
            ))}
          </ol>
        )}
        {uploads.length === 0 ? null : (
          <ul aria-live="polite" className="space-y-1 text-sm">
            {uploads.map((item) => (
              <li
                key={item.key}
                className={item.state === "failed" ? "text-destructive" : "text-muted-foreground"}
              >
                {item.state === "failed"
                  ? t("failed", { name: item.name, reason: item.reason })
                  : t(item.state, { name: item.name })}
              </li>
            ))}
          </ul>
        )}
        {photos.length < MAX_PHOTOS ? (
          <div>
            <input
              id={`${id}-photos`}
              type="file"
              accept={ACCEPT}
              multiple
              className="peer sr-only"
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []).slice(
                  0,
                  MAX_PHOTOS - photos.length,
                );
                event.target.value = "";
                for (const file of files) void add(file);
              }}
            />
            <label
              htmlFor={`${id}-photos`}
              className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-md border bg-background px-6 text-sm font-medium shadow-xs hover:bg-accent peer-focus-visible:ring-[3px] peer-focus-visible:ring-ring/50"
            >
              <ImagePlus aria-hidden className="size-4" />
              {t("addPhotos")}
            </label>
          </div>
        ) : null}
        {missing.photos ? (
          <p role="alert" className="text-sm text-destructive">
            {t("photosRequired")}
          </p>
        ) : null}
      </fieldset>

      <Choices
        id={`${id}-result`}
        legend={t("result")}
        options={RESULTS.map((value) => ({ value, label: t(`results.${value}`) }))}
        registration={form.register("result")}
        error={errors.result?.message}
      />
      <Field
        id={`${id}-notes`}
        label={t("notes")}
        hint={t("notesHint")}
        error={errors.notes?.message}
      >
        {(control) => <Textarea {...control} rows={4} {...form.register("notes")} />}
      </Field>

      <FormOutcome failure={failure} />
      <Button type="submit" size="lg" className="w-full sm:w-auto" disabled={isSubmitting}>
        {isSubmitting ? t("submitting") : t("submit")}
      </Button>
    </form>
  );
}
