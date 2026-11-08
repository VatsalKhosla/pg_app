"use client";

import type { ReactNode } from "react";

import type { BudgetExplorerText } from "./budget-explorer";
import { useLoadNear } from "./use-load-near";

const loadExplorer = () => import("./budget-explorer").then((module) => module.BudgetExplorer);

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
