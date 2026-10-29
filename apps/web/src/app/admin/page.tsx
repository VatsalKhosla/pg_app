import { redirect } from "next/navigation";

import { ADMIN_POLICIES_PATH } from "@/lib/auth/routes";

/** The admin console opens on its policies. */
export default function AdminHomePage() {
  redirect(ADMIN_POLICIES_PATH);
}
