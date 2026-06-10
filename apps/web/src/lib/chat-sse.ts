export type Citation = {
  title: string;
  source_document_id: string;
  snippet: string;
  score: number;
};

export type SseHandlers = {
  onDelta: (text: string) => void;
  onRetrieval?: (query: string) => void;
  onCitations: (citations: Citation[]) => void;
  onDone?: (finishReason: string) => void;
  onError?: (detail: string) => void;
};

/** Reads an SSE stream (event:/data: blocks) and dispatches to handlers. */
export async function consumeSse(res: Response, h: SseHandlers): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) throw new Error("no response body");
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) dispatch(block, h);
  }
  if (buffer.trim()) dispatch(buffer, h);
}

function dispatch(block: string, h: SseHandlers): void {
  let event = "";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += (data ? "\n" : "") + line.slice(5).trim();
  }
  if (!event) return;
  if (event === "delta") h.onDelta(JSON.parse(data).text as string);
  else if (event === "retrieval") h.onRetrieval?.(JSON.parse(data).query as string);
  else if (event === "citations") h.onCitations(JSON.parse(data) as Citation[]);
  else if (event === "done") h.onDone?.(JSON.parse(data).finish_reason as string);
  else if (event === "error") h.onError?.(JSON.parse(data).detail as string);
}
