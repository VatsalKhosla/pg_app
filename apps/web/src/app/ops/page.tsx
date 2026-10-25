import { redirect } from "next/navigation";

import { OPS_LISTINGS_PATH } from "@/lib/auth/routes";

/** The console opens on its listings. */
export default function OpsHomePage() {
  redirect(OPS_LISTINGS_PATH);
}
