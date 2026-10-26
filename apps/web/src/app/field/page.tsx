import { redirect } from "next/navigation";

import { FIELD_VISITS_PATH } from "@/lib/auth/routes";

/** The field screens open on the agent's visits. */
export default function FieldHomePage() {
  redirect(FIELD_VISITS_PATH);
}
