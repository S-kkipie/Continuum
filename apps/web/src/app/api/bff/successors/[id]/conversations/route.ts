import { type NextRequest, NextResponse } from "next/server";
import { forwardToApi } from "@/lib/api";
import { resolveSession } from "@/lib/bff";

export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await resolveSession();
  if (!session) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await params;
  if (!id) return NextResponse.json({ error: "bad_request" }, { status: 400 });
  try {
    const upstream = await forwardToApi(
      `successors/${id}/conversations`,
      { method: "POST", headers: { "X-User-Id": session.userId } },
      session.orgId,
    );
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "upstream_unavailable" }, { status: 503 });
  }
}
