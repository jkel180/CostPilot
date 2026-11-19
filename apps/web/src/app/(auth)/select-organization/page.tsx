"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { OrgForm } from "@/components/org-form";
import { Alert, Badge, Button } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { storeOrg } from "@/lib/current-org";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { ROLE_LABEL, type Me, type Organization } from "@/lib/types";

export default function SelectOrganizationPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    apiFetch<Me>("/me")
      .then((m) => {
        setMe(m);
        setCreating(m.memberships.length === 0);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  function choose(id: string) {
    storeOrg(id);
    router.push("/dashboard");
  }

  async function signOut() {
    storeOrg(null);
    await getSupabaseBrowserClient().auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">{creating ? "Register your organization" : "Choose an organization"}</h1>
        {me && <p className="mt-1 text-sm text-muted">Signed in as {me.user.email}</p>}
      </div>
      {error && <Alert>{error}</Alert>}
      {!me && !error && <p className="text-sm text-muted">Loading…</p>}

      {me && !creating && (
        <ul className="divide-y divide-border rounded-md border border-border">
          {me.memberships.map((m) => (
            <li key={m.organization_id}>
              <button
                onClick={() => choose(m.organization_id)}
                className="flex w-full items-center justify-between px-3.5 py-3 text-left text-sm hover:bg-background"
              >
                <span className="font-medium">{m.organization_name}</span>
                <Badge tone={m.role === "admin" ? "accent" : "neutral"}>{ROLE_LABEL[m.role]}</Badge>
              </button>
            </li>
          ))}
        </ul>
      )}

      {me && creating && (
        <>
          {me.memberships.length === 0 && (
            <p className="text-sm text-muted">
              You will be the organization&apos;s admin. To join an existing organization instead, ask its admin to add{" "}
              {me.user.email}.
            </p>
          )}
          <OrgForm
            submitLabel="Create organization"
            onSubmit={async (values) => {
              const org = await apiFetch<Organization>("/organizations", { method: "POST", body: values });
              choose(org.id);
            }}
          />
        </>
      )}

      {me && (
        <div className="flex items-center justify-between border-t border-border pt-4">
          {me.memberships.length > 0 ? (
            <Button variant="ghost" onClick={() => setCreating(!creating)} className="px-0">
              {creating ? "Back to my organizations" : "+ Register a new organization"}
            </Button>
          ) : (
            <span />
          )}
          <Button variant="ghost" onClick={signOut}>
            Sign out
          </Button>
        </div>
      )}
    </div>
  );
}
