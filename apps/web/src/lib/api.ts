const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";
const SERVICE_TOKEN = process.env.SERVICE_TOKEN ?? "dev-shared-service-token";

export async function callApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "X-Service-Token": SERVICE_TOKEN },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return (await res.json()) as T;
}
