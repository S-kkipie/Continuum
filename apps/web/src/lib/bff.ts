import { headers } from "next/headers";
import { auth } from "@/lib/auth";

/** Resolve the caller's active org id from the Better Auth session (server-side only). */
export async function resolveOrgId(): Promise<string | null> {
  const session = await auth.api.getSession({ headers: await headers() });
  return session?.user && session.session?.activeOrganizationId
    ? session.session.activeOrganizationId
    : null;
}
