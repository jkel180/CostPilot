# CostPilot AI — web

Next.js 16 (App Router) + TypeScript + Tailwind CSS 4 + Recharts. Auth via Supabase (`@supabase/ssr`).

- `src/proxy.ts` — refreshes the Supabase session and redirects signed-out users to `/login` (optimistic only; the API is the security boundary).
- `src/components/org-context.tsx` — loads `/me`, resolves the current organization and scopes every API call with `X-Organization-Id`.
- `src/app/(auth)` — login, sign-up, password recovery, organization selection / registration.
- `src/app/(app)` — dashboard, settings and the module pages.

See the root `README.md` for setup.
