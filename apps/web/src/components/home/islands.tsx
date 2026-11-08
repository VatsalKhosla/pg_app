"use client";

import type { ReactNode } from "react";

import type { BudgetExplorerText } from "./budget-explorer";
import type { StaySimulatorProps } from "./stay-simulator";
import { useLoadNear } from "./use-load-near";

const loadSimulator = () => import("./stay-simulator").then((module) => module.StaySimulator);
const loadExplorer = () => import("./budget-explorer").then((module) => module.BudgetExplorer);

/** The stay simulator, once it nears the screen; before that, the steps the server wrote. */
export function StaySimulatorNear({
  children,
  ...props
}: StaySimulatorProps & { children: ReactNode }) {
  const { ref, Loaded } = useLoadNear(loadSimulator);
  return <div ref={ref}>{Loaded === null ? children : <Loaded {...props} />}</div>;
}

/** The budget explorer, once it nears the screen; before that, a link to search. */
export function BudgetExplorerNear({
  text,
  children,
}: {
  text: BudgetExplorerText;
  children: ReactNode;
}) {
  const { ref, Loaded } = useLoadNear(loadExplorer);
  return (
    <div ref={ref}>{Loaded === null ? children : <Loaded text={text}>{children}</Loaded>}</div>
  );
}
