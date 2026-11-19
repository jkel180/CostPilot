"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useOrg } from "@/components/org-context";
import { Badge, Logo } from "@/components/ui";
import { storeOrg } from "@/lib/current-org";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { ROLE_LABEL } from "@/lib/types";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/market", label: "Market Intelligence" },
  { href: "/forecasting", label: "Forecasting" },
  { href: "/purchases", label: "My Purchases" },
  { href: "/simulator", label: "Cost Simulator" },
  { href: "/insights", label: "AI Insights" },
  { href: "/settings", label: "Settings" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { me, current, switchOrg } = useOrg();
  const [menuOpen, setMenuOpen] = useState(false);

  async function signOut() {
    storeOrg(null);
    await getSupabaseBrowserClient().auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  const nav = (
    <nav className="flex flex-col gap-0.5" aria-label="Main">
      {NAV.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setMenuOpen(false)}
            aria-current={active ? "page" : undefined}
            className={`rounded-md px-3 py-2 text-sm ${
              active ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-background hover:text-foreground"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[232px_1fr]">
      <aside className="hidden border-r border-border bg-surface lg:flex lg:flex-col">
        <div className="px-5 py-5">
          <Logo />
        </div>
        <div className="flex-1 px-3">{nav}</div>
        <div className="border-t border-border px-5 py-4 text-xs text-muted">
          <p className="truncate" title={me.user.email}>
            {me.user.email}
          </p>
          <button onClick={signOut} className="mt-1 text-accent hover:underline">
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-10 flex h-14 items-center justify-between gap-3 border-b border-border bg-surface/95 px-4 backdrop-blur sm:px-6">
          <div className="flex items-center gap-3">
            <button
              className="rounded-md p-1.5 text-muted hover:bg-background lg:hidden"
              onClick={() => setMenuOpen(!menuOpen)}
              aria-label="Toggle navigation"
              aria-expanded={menuOpen}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden>
                <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </button>
            <span className="lg:hidden">
              <Logo />
            </span>
          </div>
          <div className="flex min-w-0 items-center gap-2">
            {me.memberships.length > 1 ? (
              <select
                aria-label="Organization"
                value={current.organization_id}
                onChange={(e) => switchOrg(e.target.value)}
                className="h-8 max-w-48 truncate rounded-md border border-border bg-surface px-2 text-sm"
              >
                {me.memberships.map((m) => (
                  <option key={m.organization_id} value={m.organization_id}>
                    {m.organization_name}
                  </option>
                ))}
              </select>
            ) : (
              <span className="truncate text-sm font-medium">{current.organization_name}</span>
            )}
            <Badge tone={current.role === "admin" ? "accent" : "neutral"}>{ROLE_LABEL[current.role]}</Badge>
          </div>
        </header>
        {menuOpen && (
          <div className="border-b border-border bg-surface px-3 py-3 lg:hidden">
            {nav}
            <button onClick={signOut} className="mt-2 px-3 text-sm text-accent">
              Sign out
            </button>
          </div>
        )}
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions}
    </div>
  );
}
