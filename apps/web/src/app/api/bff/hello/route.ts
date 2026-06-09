import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { callApi } from "@/lib/api";
import { auth } from "@/lib/auth";

export async function GET() {
  // Session is optional for the walking skeleton; a DB blip must not crash the route.
  let session: Awaited<ReturnType<typeof auth.api.getSession>> = null;
  try {
    session = await auth.api.getSession({ headers: await headers() });
  } catch {
    // session stays null (non-fatal)
  }

  try {
    const upstream = await callApi<{ from: string; db: string }>("/internal/hello");
    return NextResponse.json({
      from: "bff",
      authenticated: Boolean(session?.user),
      user: session?.user?.email ?? null,
      upstream,
    });
  } catch (err) {
    // 502 = upstream replied non-OK; 503 = upstream unreachable
    const status = err instanceof Error && err.message.includes("failed:") ? 502 : 503;
    return NextResponse.json({ error: "upstream_unavailable" }, { status });
  }
}
