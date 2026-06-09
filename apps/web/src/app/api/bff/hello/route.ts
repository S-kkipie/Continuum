import { NextResponse } from "next/server";
import { headers } from "next/headers";
import { auth } from "@/lib/auth";
import { callApi } from "@/lib/api";

export async function GET() {
  const session = await auth.api.getSession({ headers: await headers() });

  // Walking skeleton: session is optional here so the chain is demoable pre-login.
  // Spec 1+ routes will require it.
  const upstream = await callApi<{ from: string; db: string }>("/internal/hello");

  return NextResponse.json({
    from: "bff",
    authenticated: Boolean(session?.user),
    user: session?.user?.email ?? null,
    upstream,
  });
}
