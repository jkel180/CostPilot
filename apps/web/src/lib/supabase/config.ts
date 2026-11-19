export type SupabaseConfig = { url: string; key: string };

/** Public Supabase settings. Returns null when the app has not been configured yet. */
export function getSupabaseConfig(): SupabaseConfig | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  return url && key ? { url, key } : null;
}

export function requireSupabaseConfig(): SupabaseConfig {
  const cfg = getSupabaseConfig();
  if (!cfg) {
    throw new Error(
      "Supabase is not configured: set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY in apps/web/.env.local",
    );
  }
  return cfg;
}
