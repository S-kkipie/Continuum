import { type NextRequest, NextResponse } from "next/server";
import { forwardToApi } from "@/lib/api";
import { resolveOrgId } from "@/lib/bff";

export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const orgId = await resolveOrgId();
  if (!orgId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await params;
  if (!id) return NextResponse.json({ error: "bad_request" }, { status: 400 });
  try {
    const upstream = await forwardToApi(
      `successors/${id}/conversations`,
      { method: "POST" },
      orgId,
    );
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "upstream_unavailable" }, { status: 503 });
  }
}
