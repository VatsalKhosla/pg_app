"use client";

import type { Route } from "next";
import { useRouter } from "next/navigation";

import { AddOwner } from "./owner-picker";

/** Add an owner from the owners page, then open theirs. */
export function AddOwnerPanel() {
  const router = useRouter();
  return (
    <AddOwner
      onAdded={(owner) => {
        router.push(`/ops/owners/${owner.id}` as Route);
      }}
    />
  );
}
