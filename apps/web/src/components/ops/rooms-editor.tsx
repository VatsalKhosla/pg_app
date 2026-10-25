"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import type { Schemas } from "@pg-platform/api-client";
import { Pencil, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { showFieldErrors } from "@/lib/forms/field-errors";
import { z } from "@/lib/forms/zod";
import { formatINR } from "@/lib/money";
import { addBed, addRoom, type Listing, setBedStatus, updateCategory } from "@/lib/ops/client";

import { CategoryForm } from "./category-form";
import { Field, FormOutcome, Select } from "./fields";
import { useOpsProblem } from "./problems";
import { useRefresh } from "./use-refresh";

type Category = Schemas["CategoryInfo"];
type Room = Schemas["RoomInfo"];

/** The API's limits for rooms and beds (apps/api/src/app/modules/catalog/domain/rooms.py). */
const LABEL_MAX = 80;
const LOWEST_FLOOR = -3;
const HIGHEST_FLOOR = 60;

/** What a listing sells: its room categories, their rooms, and the beds in each. */
export function RoomsEditor({ listing }: { listing: Listing }) {
  const t = useTranslations("Ops.rooms");
  const [adding, setAdding] = useState(false);

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">{t("intro")}</p>
      {listing.categories.map((category) => (
        <CategoryCard key={category.id} listingId={listing.id} category={category} />
      ))}
      {adding ? (
        <CategoryForm
          listingId={listing.id}
          onDone={() => {
            setAdding(false);
          }}
        />
      ) : (
        <Button
          type="button"
          variant="outline"
          size="lg"
          onClick={() => {
            setAdding(true);
          }}
        >
          <Plus aria-hidden />
          {t("addCategory")}
        </Button>
      )}
    </div>
  );
}

function CategoryCard({ listingId, category }: { listingId: string; category: Category }) {
  const t = useTranslations("Ops");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const offered = category.status === "active";
  const features = [
    category.ac ? t("rooms.ac") : null,
    category.attachedBath ? t("rooms.attachedBath") : null,
    category.balcony ? t("rooms.balcony") : null,
  ].filter((feature) => feature !== null);

  async function toggleOffered() {
    setFailure(null);
    setBusy(true);
    try {
      await updateCategory(category.id, { status: offered ? "inactive" : "active" });
      refresh();
    } catch (error) {
      setFailure(problem(error));
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <CategoryForm
        listingId={listingId}
        category={category}
        onDone={() => {
          setEditing(false);
        }}
      />
    );
  }
  return (
    <article aria-labelledby={`${id}-title`} className="space-y-4 rounded-md border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 id={`${id}-title`} className="font-semibold">
            {category.label}
          </h3>
          <p className="text-sm text-muted-foreground">
            {[t(`occupancy.${category.occupancy}`), ...features].join(" · ")}
          </p>
          <p className="text-sm">
            {t("rooms.summary", {
              rent: formatINR(category.baseRentPaise),
              deposit: formatINR(category.securityDepositPaise),
            })}
          </p>
          {category.monthlyChargesPaise > 0 || category.oneTimeChargesPaise > 0 ? (
            <p className="text-sm text-muted-foreground">
              {t("rooms.extras", {
                monthly: formatINR(category.monthlyChargesPaise),
                once: formatINR(category.oneTimeChargesPaise),
              })}
            </p>
          ) : null}
          <p className="text-sm font-medium">
            {offered ? t("rooms.offered") : t("rooms.notOffered")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setEditing(true);
            }}
          >
            <Pencil aria-hidden />
            {t("rooms.editCategory", { label: category.label })}
          </Button>
          <Button
            type="button"
            variant="ghost"
            disabled={busy}
            onClick={() => {
              void toggleOffered();
            }}
          >
            {offered ? t("rooms.stopOffering") : t("rooms.offer")}
          </Button>
        </div>
      </div>
      <FormOutcome failure={failure} />

      {category.rooms.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("rooms.noRooms")}</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {category.rooms.map((room) => (
            <li key={room.id} className="p-3">
              <RoomRow room={room} bedsPerRoom={category.bedsPerRoom} />
            </li>
          ))}
        </ul>
      )}
      <AddRoomForm category={category} />
    </article>
  );
}

function RoomRow({ room, bedsPerRoom }: { room: Room; bedsPerRoom: number }) {
  const t = useTranslations("Ops.rooms");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function toggleBed(bed: Room["beds"][number]) {
    setFailure(null);
    setBusy(bed.id);
    try {
      await setBedStatus(bed.id, bed.status === "active" ? "inactive" : "active");
      refresh();
    } catch (error) {
      setFailure(problem(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-3">
      <p className="font-medium">
        {t("room", { label: room.label })}
        {room.floor === null ? null : (
          <span className="font-normal text-muted-foreground">
            {" · "}
            {t("floor", { floor: room.floor })}
          </span>
        )}
      </p>
      <ul className="flex flex-wrap gap-2">
        {room.beds.map((bed) => (
          <li key={bed.id} className="flex items-center gap-2 rounded-md border px-3 py-1 text-sm">
            <span>
              {t("bed", { label: bed.label })}:{" "}
              {bed.status === "active" ? t("bedInUse") : t("bedOutOfUse")}
            </span>
            <Button
              type="button"
              variant="link"
              size="sm"
              disabled={busy !== null}
              onClick={() => {
                void toggleBed(bed);
              }}
            >
              {bed.status === "active"
                ? t("takeOut", { label: bed.label })
                : t("putBack", { label: bed.label })}
            </Button>
          </li>
        ))}
      </ul>
      <FormOutcome failure={failure} />
      {room.beds.length < bedsPerRoom ? <AddBedForm room={room} /> : null}
    </div>
  );
}

function AddRoomForm({ category }: { category: Category }) {
  const t = useTranslations("Ops");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    label: z
      .string()
      .trim()
      .min(1, t("validation.required"))
      .max(LABEL_MAX, t("validation.tooLong")),
    floor: z
      .string()
      .trim()
      .refine(
        (text) => {
          if (text === "") return true;
          const floor = Number(text);
          return Number.isInteger(floor) && LOWEST_FLOOR <= floor && floor <= HIGHEST_FLOOR;
        },
        t("validation.floor", { lowest: LOWEST_FLOOR, highest: HIGHEST_FLOOR }),
      ),
    beds: z.string(),
  });
  type Values = z.infer<typeof schema>;
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { label: "", floor: "", beds: String(category.bedsPerRoom) },
  });
  const { errors, isSubmitting } = form.formState;

  async function add(values: Values) {
    setFailure(null);
    try {
      await addRoom(category.id, {
        label: values.label,
        floor: values.floor === "" ? null : Number(values.floor),
        beds: Number(values.beds),
      });
      form.reset();
      refresh();
    } catch (error) {
      const shown = showFieldErrors(error, form.setError, (pointer) =>
        pointer === "/label" ? "label" : pointer === "/floor" ? "floor" : undefined,
      );
      if (!shown) setFailure(problem(error));
    }
  }

  return (
    <form
      noValidate
      aria-label={t("rooms.addRoomTo", { label: category.label })}
      className="space-y-4"
      onSubmit={(event) => {
        void form.handleSubmit(add)(event);
      }}
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <Field id={`${id}-label`} label={t("rooms.roomLabel")} error={errors.label?.message}>
          {(control) => <Input {...control} autoComplete="off" {...form.register("label")} />}
        </Field>
        <Field id={`${id}-floor`} label={t("rooms.roomFloor")} error={errors.floor?.message}>
          {(control) => (
            <Input
              {...control}
              inputMode="numeric"
              autoComplete="off"
              {...form.register("floor")}
            />
          )}
        </Field>
        <Field id={`${id}-beds`} label={t("rooms.beds")}>
          {(control) => (
            <Select {...control} {...form.register("beds")}>
              {Array.from({ length: category.bedsPerRoom + 1 }, (_, count) => (
                <option key={count} value={String(count)}>
                  {count}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <FormOutcome failure={failure} />
      <Button type="submit" variant="secondary" disabled={isSubmitting}>
        <Plus aria-hidden />
        {t("rooms.createRoom")}
      </Button>
    </form>
  );
}

function AddBedForm({ room }: { room: Room }) {
  const t = useTranslations("Ops");
  const problem = useOpsProblem();
  const refresh = useRefresh();
  const id = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    label: z
      .string()
      .trim()
      .min(1, t("validation.required"))
      .max(LABEL_MAX, t("validation.tooLong")),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { label: "" },
  });
  const error = form.formState.errors.label?.message;

  async function add({ label }: { label: string }) {
    setFailure(null);
    try {
      await addBed(room.id, label);
      form.reset();
      refresh();
    } catch (failed) {
      const shown = showFieldErrors(failed, form.setError, (pointer) =>
        pointer === "/label" ? "label" : undefined,
      );
      if (!shown) setFailure(problem(failed));
    }
  }

  return (
    <form
      noValidate
      aria-label={t("rooms.addBedTo", { label: room.label })}
      className="flex flex-wrap items-end gap-3"
      onSubmit={(event) => {
        void form.handleSubmit(add)(event);
      }}
    >
      <Field id={`${id}-label`} label={t("rooms.bedLabel")} error={error} className="w-40">
        {(control) => <Input {...control} autoComplete="off" {...form.register("label")} />}
      </Field>
      <Button type="submit" variant="secondary" disabled={form.formState.isSubmitting}>
        <Plus aria-hidden />
        {t("rooms.addBed")}
      </Button>
      <div className="w-full">
        <FormOutcome failure={failure} />
      </div>
    </form>
  );
}
