import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";

const connectionString = process.env.DATABASE_URL;
if (!connectionString) throw new Error("DATABASE_URL is not set");

// `pool` is exported because the Better Auth Drizzle adapter needs the raw Pool.
// For application queries, prefer `db` (typed, schema-aware) over raw pool access.
export const pool = new Pool({
  connectionString,
  max: Number(process.env.DB_POOL_MAX ?? 10),
  idleTimeoutMillis: Number(process.env.DB_IDLE_TIMEOUT_MS ?? 30_000),
  connectionTimeoutMillis: Number(process.env.DB_CONN_TIMEOUT_MS ?? 5_000),
});
export const db = drizzle(pool);
