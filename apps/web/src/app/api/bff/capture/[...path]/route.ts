import { headers } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";
import { forwardToApi } from "@/lib/api";
import { auth } from "@/lib/auth";

async function resolveOrg(): Promise<{ userId: string; orgId: string } | null> {
  const session = await auth.api.getSession({ headers: await headers() });
  const orgId = session?.session?.activeOrganizationId;
  if (!session?.user || !orgId) return null;
  // userId is returned for forwarding as X-User-Id in Spec 2 (chat proxy); unused here.
  return { userId: session.user.id, orgId };
}

async function handle(req: NextRequest, path: string[]): Promise<Response> {
  const ctx = await resolveOrg();
  if (!ctx) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const init: RequestInit = { method: req.method };
  if (req.method !== "GET") init.body = await req.arrayBuffer();
  const contentType = req.headers.get("content-type");
  if (contentType) init.headers = { "content-type": contentType };

  try {
    const upstream = await forwardToApi(path.join("/"), init, ctx.orgId);
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json({ error: "upstream_unavailable" }, { status: 503 });
  }
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
