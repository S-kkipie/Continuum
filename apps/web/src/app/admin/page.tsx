"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type Snippet = { content: string; source_document_id: string; score: number };

async function bff(path: string, init?: RequestInit) {
  const res = await fetch(`/api/bff/capture/${path}`, init);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export default function Admin() {
  const [title, setTitle] = useState("Support Lead");
  const [file, setFile] = useState<File | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [snippets, setSnippets] = useState<Snippet[]>([]);
  const [running, setRunning] = useState(false);
  const say = (m: string) => setLog((l) => [...l, m]);

  async function run() {
    if (running) return;
    setRunning(true);
    setLog([]);
    setSnippets([]);
    try {
      const roleId = `r-${crypto.randomUUID().slice(0, 8)}`;
      say(`creating role ${roleId}…`);
      await bff("roles", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ id: roleId, title }),
      });
      const succ = await bff(`roles/${roleId}/successor`, { method: "POST" });
      say(`successor ${succ.id} (${succ.status})`);
      if (file) {
        const fd = new FormData();
        fd.append("files", file);
        await bff(`successors/${succ.id}/documents`, { method: "POST", body: fd });
        say(`uploaded ${file.name}`);
      }
      const job = await bff(`successors/${succ.id}/ingest`, { method: "POST" });
      say(`ingest job ${job.job_id}: ${job.status}`);
      const s = await bff(`successors/${succ.id}`);
      say(`successor status: ${s.status}`);
      const q = await bff(`successors/${succ.id}/query`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query: "what should I know" }),
      });
      setSnippets(q.snippets);
    } catch (err) {
      say(`ERROR: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl space-y-4 p-8">
      <h1 className="text-2xl font-semibold">Continuum — Capture (admin)</h1>
      <Card className="space-y-3 p-4">
        <input
          className="w-full rounded-md border border-border bg-background px-3 py-2"
          placeholder="Role title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <input
          type="file"
          accept=".txt,.md"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <Button
          disabled={running}
          onClick={() => {
            void run();
          }}
        >
          {running ? "Running…" : "Build successor from doc"}
        </Button>
      </Card>
      {log.length > 0 && (
        <Card className="p-4">
          <pre className="whitespace-pre-wrap text-sm">{log.join("\n")}</pre>
        </Card>
      )}
      {snippets.length > 0 && (
        <Card className="space-y-2 p-4">
          <p className="font-medium">Retrieved knowledge</p>
          {snippets.map((s) => (
            <div
              key={`${s.source_document_id}::${s.content.slice(0, 40)}`}
              className="rounded-md bg-muted/40 p-2 text-sm"
            >
              <span className="text-muted-foreground">{s.source_document_id}</span>
              <p>{s.content}</p>
            </div>
          ))}
        </Card>
      )}
    </main>
  );
}
