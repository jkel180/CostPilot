"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { readStoredOrg, storeOrg } from "@/lib/current-org";
import type { Me, MembershipSummary, Role } from "@/lib/types";

type OrgState = {
  me: Me;
  current: MembershipSummary;
  role: Role;
  /** Fetch scoped to the current organization. */
  api: <T>(path: string, opts?: { method?: "GET" | "POST" | "PATCH" | "DELETE"; body?: unknown }) => Promise<T>;
  switchOrg: (id: string) => void;
  reload: () => Promise<void>;
};

const Ctx = createContext<OrgState | null>(null);

export function useOrg(): OrgState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useOrg must be used inside <OrgProvider>");
  return v;
}

export function OrgProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [orgId, setOrgId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const m = await apiFetch<Me>("/me");
      const stored = readStoredOrg();
      const chosen =
        m.memberships.find((x) => x.organization_id === stored) ??
        (m.memberships.length === 1 ? m.memberships[0] : undefined);
      if (!chosen) {
        storeOrg(null);
        router.replace("/select-organization");
        return;
      }
      storeOrg(chosen.organization_id);
      setMe(m);
      setOrgId(chosen.organization_id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.replace("/login");
      else setError(e instanceof Error ? e.message : "Could not load your account");
    }
  }, [router]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data load
    void load();
  }, [load]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="max-w-md rounded-lg border border-border bg-surface p-6 text-sm">
          <p className="font-medium text-negative">{error}</p>
          <button onClick={() => { setError(null); void load(); }} className="mt-3 text-accent hover:underline">
            Retry
          </button>
        </div>
      </div>
    );
  }
  const current = me?.memberships.find((x) => x.organization_id === orgId);
  if (!me || !current) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted">Loading…</div>;
  }

  const value: OrgState = {
    me,
    current,
    role: current.role,
    api: (path, opts) => apiFetch(path, { ...opts, orgId: current.organization_id }),
    switchOrg: (id) => {
      storeOrg(id);
      setOrgId(id);
    },
    reload: load,
  };
  // key: remount pages on organization switch so no data from the previous org lingers
  return (
    <Ctx.Provider value={value}>
      <div key={current.organization_id} className="contents">
        {children}
      </div>
    </Ctx.Provider>
  );
}
