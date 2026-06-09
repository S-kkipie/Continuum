"use client";

import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";

type Hello = {
  from: string;
  authenticated: boolean;
  user: string | null;
  upstream: { from: string; db: string };
};

export default function Home() {
  const { data, isLoading, error } = useQuery<Hello>({
    queryKey: ["bff-hello"],
    queryFn: async () => {
      const res = await fetch("/api/bff/hello");
      if (!res.ok) throw new Error("BFF failed");
      return res.json();
    },
  });

  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="text-2xl font-semibold">Continuum — Walking Skeleton</h1>
      <Card className="mt-4 p-4">
        {isLoading && <p>checking chain…</p>}
        {error && <p className="text-red-600">chain broken: {String(error)}</p>}
        {data && (
          <pre className="text-sm" data-testid="chain">
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
      </Card>
    </main>
  );
}
