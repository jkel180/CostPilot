import type { ReactNode } from "react";
import { Logo } from "@/components/ui";
import { getSupabaseConfig } from "@/lib/supabase/config";

export default function AuthLayout({ children }: { children: ReactNode }) {
  const configured = getSupabaseConfig() !== null;
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Logo />
        </div>
        {!configured && (
          <div className="mb-4 rounded-md bg-warning-soft px-3 py-2 text-xs leading-relaxed text-warning">
            Supabase is not configured. Set <code>NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
            <code>NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY</code> in <code>apps/web/.env.local</code>.
          </div>
        )}
        <div className="rounded-lg border border-border bg-surface p-6 shadow-[0_1px_2px_rgba(11,27,51,0.04)]">{children}</div>
        <p className="mt-6 text-center text-xs text-subtle">Commodity cost intelligence for Food &amp; Beverage</p>
      </div>
    </main>
  );
}
