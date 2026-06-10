import { type NextRequest, NextResponse } from "next/server";
import { forwardToApi } from "@/lib/api";
import { resolveOrgId } from "@/lib/bff";

async function handle(req: NextRequest, path: string[]): Promise<Response> {
  const orgId = await resolveOrgId();
  if (!orgId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const init: RequestInit = { method: req.method };
  if (req.method !== "GET") init.body = await req.arrayBuffer();
  const contentType = req.headers.get("content-type");
  if (contentType) init.headers = { "content-type": contentType };
  try {
    const upstream = await forwardToApi(`conversations/${path.join("/")}`, init, orgId);
    // Stream the body straight through (SSE). Do NOT await .text()/.json() — that buffers.
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-cache, no-transform",
        "x-accel-buffering": "no",
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
