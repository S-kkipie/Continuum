import { headers } from "next/headers";
import { auth } from "@/lib/auth";

/** Resolve the caller's active org id from the Better Auth session (server-side only). */
export async function resolveOrgId(): Promise<string | null> {
  const session = await auth.api.getSession({ headers: await headers() });
  return session?.user && session.session?.activeOrganizationId
    ? session.session.activeOrganizationId
    : null;
}

/** Resolve both the user id and active org id (server-side only). */
export async function resolveSession(): Promise<{ userId: string; orgId: string } | null> {
  const session = await auth.api.getSession({ headers: await headers() });
  const orgId = session?.session?.activeOrganizationId;
  if (!session?.user || !orgId) return null;
  return { userId: session.user.id, orgId };
}
