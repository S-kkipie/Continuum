"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { type Citation, consumeSse } from "@/lib/chat-sse";

type Msg = { role: "user" | "assistant"; content: string; citations?: Citation[] };

export function MentorChat({ successorId }: { successorId: string }) {
  const [, setConversationId] = useState<string | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function ensureConversation(): Promise<string> {
    if (conversationIdRef.current) return conversationIdRef.current;
    const res = await fetch(`/api/bff/successors/${successorId}/conversations`, { method: "POST" });
    if (!res.ok) throw new Error(`conversation -> ${res.status}`);
    const id = (await res.json()).id as string;
    conversationIdRef.current = id;
    setConversationId(id);
    return id;
  }

  async function send() {
    if (busy || !input.trim()) return;
    setBusy(true);
    const content = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", content }, { role: "assistant", content: "" }]);
    try {
      const id = await ensureConversation();
      const res = await fetch(`/api/bff/conversations/${id}/messages`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error(`message -> ${res.status}`);
      await consumeSse(res, {
        onRetrieval: (query) =>
          setMessages((m) => {
            const next = [...m];
            const last = next[next.length - 1];
            if (last.role === "assistant" && last.content === "") {
              next[next.length - 1] = { ...last, content: `🔎 searching: ${query}…` };
            }
            return next;
          }),
        onDelta: (t) =>
          setMessages((m) => {
            const next = [...m];
            const last = next[next.length - 1];
            // first delta clears the transient "searching…" placeholder
            const base = last.content.startsWith("🔎 searching") ? "" : last.content;
            next[next.length - 1] = { ...last, content: base + t };
            return next;
          }),
        onCitations: (c) =>
          setMessages((m) => {
            const next = [...m];
            next[next.length - 1] = { ...next[next.length - 1], citations: c };
            return next;
          }),
        onError: (detail) =>
          setMessages((m) => {
            const next = [...m];
            next[next.length - 1] = { role: "assistant", content: `ERROR: ${detail}` };
            return next;
          }),
      });
    } catch (err) {
      setMessages((m) => {
        const next = [...m];
        next[next.length - 1] = {
          role: "assistant",
          content: `ERROR: ${err instanceof Error ? err.message : String(err)}`,
        };
        return next;
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 p-6">
      <h1 className="text-xl font-semibold">Ask your role&apos;s AI successor</h1>
      <div className="flex flex-col gap-3">
        {messages.map((m, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: append-only list
          <Card key={`${m.role}-${i}`} className="p-3 text-sm">
            <p className="mb-1 text-xs text-muted-foreground">{m.role}</p>
            <p className="whitespace-pre-wrap">{m.content || "…"}</p>
            {m.citations && m.citations.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {m.citations.map((c) => (
                  <span
                    key={`${c.source_document_id}::${c.snippet.slice(0, 24)}`}
                    className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                    title={c.snippet}
                  >
                    {c.source_document_id}
                  </span>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          className="flex-1 rounded-md border border-border bg-background px-3 py-2"
          placeholder="Why do we…?"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void send();
          }}
        />
        <Button disabled={busy} onClick={() => void send()}>
          {busy ? "…" : "Ask"}
        </Button>
      </div>
    </div>
  );
}
