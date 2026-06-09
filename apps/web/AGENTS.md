<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# apps/web — Continuum web app

Next.js 16 (App Router) · React 19 · TypeScript · Tailwind v4 · shadcn/ui · TanStack (Query/Table/Form) · Better Auth · assistant-ui. Package name: `web`. Part of a pnpm/Turborepo workspace — see the repo `README.md` for the monorepo map and `docs/context/` for project state.

## Commands (from repo root)

- Dev: `pnpm --filter web dev` (or `pnpm dev` for web + api together).
- Build: `pnpm --filter web build`.
- Typecheck: `pnpm --filter web typecheck`.
- Lint/format: `pnpm check` (Biome, whole repo) or `pnpm --filter web lint`. Apply safe fixes: `pnpm fix`.
- E2E: `pnpm --filter web exec playwright test` (services up; override target with `PLAYWRIGHT_BASE_URL`).

## Tooling

- **Biome, not ESLint.** Do not add ESLint config or scripts. `biome.json` lives at the repo root (2-space, double quotes, line width 100). Run `pnpm fix` before committing.
- 2-space indent. Preserve existing naming and import style.

## Code style

- Do not use `any`, `as any`, `as unknown as`, `@ts-ignore`, or `@ts-expect-error` to silence type errors. Prefer explicit types, clear names, early returns, narrow module boundaries.
- Small, focused changes. Do not refactor unrelated code while fixing or adding a feature. Keep files under ~500 lines; split into modules, components, hooks, or helpers.
- Keep business logic out of UI components when it can live in typed utilities, hooks, or server modules.

## TSDoc is opt-in, not mandatory

Document an API only when it adds information not inferable from the name, params, types, file name, or surrounding code — reusable libraries, hooks with non-obvious behavior, business rules, caching/concurrency/side effects, invariants, security-sensitive code. Do NOT document React components, pages, layouts, presentational components, simple wrappers, or obvious getters/CRUD. If the summary would just restate the name, omit it. Prefer expressive code over comments.

## Styling (Tailwind v4 + shadcn)

- `src/app/globals.css` is the single source of truth for design tokens (shadcn base-nova: `--primary`, `--card`, `--border`, `--ring`, `--radius`, chart/sidebar tokens). Read it before styling.
- Map colors to semantic tokens (`primary`/`destructive`/`muted`/`border`/`card`). Never hardcode palette colors (`text-zinc-900`, `bg-white`). Use the `/10` opacity form for soft tinted surfaces (`bg-destructive/10`).
- No manual `dark:` color overrides — tokens invert automatically through the `.dark` block.
- Prefer Tailwind scale utilities over arbitrary px (Tailwind v4 dynamic spacing). Use arbitrary px only when no scale step fits (off-scale px, `rounded-[Npx]` off the radius scale, real units, `leading-[..]`, `tracking-[..]`).
- Do not restyle `src/components/ui/*` (vendored shadcn primitives).
- Biome does not format CSS (Tailwind v4 at-rules like `@theme`/`@custom-variant` aren't parseable) — don't expect `pnpm fix` to touch `globals.css`.

## Architecture (this app)

- **Auth**: Better Auth — `src/lib/auth.ts` (server: Microsoft/Entra provider + Organization plugin, Drizzle adapter over `@continuum/db`), `src/lib/auth-client.ts` (client). Route handler at `src/app/api/auth/[...all]/route.ts`.
- **BFF pattern**: the browser talks only to Next.js. Server routes under `src/app/api/bff/*` validate the Better Auth session, then call the Python API via `src/lib/api.ts` (sends `X-Service-Token`). FastAPI is never called directly from the browser. Reference shape: `src/app/api/bff/hello/route.ts` (tolerates a missing session; maps upstream failure to 502/503).
- **Data fetching**: TanStack Query — provider in `src/app/providers.tsx` (`retry: false`).

## Env

- Next loads env from **`apps/web/.env.local`** (gitignored), NOT the repo root. Required keys: `DATABASE_URL`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`, `NEXT_PUBLIC_BETTER_AUTH_URL`, `MICROSOFT_CLIENT_ID/SECRET/TENANT_ID`, `API_BASE_URL`, `SERVICE_TOKEN`. See repo `README.md` step 2.
- `@continuum/db` throws at import if `DATABASE_URL` is unset — keep it in `.env.local`.

## Verification

- After changes: `pnpm --filter web typecheck` + `pnpm check`. For runtime/routing/server/build changes: `pnpm --filter web build`. For UI: verify in a browser at `http://localhost:3000` (free port 3000 first — another local app may occupy it).
