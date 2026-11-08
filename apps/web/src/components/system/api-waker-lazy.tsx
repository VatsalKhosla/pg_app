"use client";

import dynamic from "next/dynamic";
import type { ComponentProps } from "react";

import type { ApiWaker as Waker } from "./api-waker";

const ApiWaker = dynamic(() => import("./api-waker").then((module) => module.ApiWaker), {
  ssr: false,
});

/** The waker's code loads only on the test site, after the page, so no other build pays for it. */
export function ApiWakerLazy(props: ComponentProps<typeof Waker>) {
  return <ApiWaker {...props} />;
}
