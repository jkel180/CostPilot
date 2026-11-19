"use client";

import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "@/components/app-shell";
import { OrgForm } from "@/components/org-form";
import { useOrg } from "@/components/org-context";
import { Alert, Badge, Button, Card, EmptyState, Input, Select } from "@/components/ui";
import { ROLE_LABEL, type Member, type Organization, type Role } from "@/lib/types";

const ROLES: Role[] = ["admin", "analyst", "viewer"];

export default function SettingsPage() {
  const { api, role, me, reload, current } = useOrg();
  const isAdmin = role === "admin";
  const [org, setOrg] = useState<Organization | null>(null);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function refresh() {
    try {
      const [o, m] = await Promise.all([api<Organization>("/organizations/current"), api<Member[]>("/organizations/current/members")]);
      setOrg(o);
      setMembers(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load settings");
    }
  }

  useEffect(() => {
    // initial data load; refresh() only sets state after the requests resolve
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current.organization_id]);

  async function run(action: () => Promise<unknown>, success: string) {
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    }
  }

  async function addMember(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formEl = e.currentTarget;
    const f = new FormData(formEl);
    await run(
      () => api("/organizations/current/members", { method: "POST", body: { email: f.get("email"), role: f.get("role") } }),
      "Member added.",
    );
    formEl.reset();
  }

  return (
    <>
      <PageHeader title="Settings" description="Organization profile and user access." />
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {notice && <Alert tone="positive">{notice}</Alert>}

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,420px)_1fr]">
          <Card title="Organization profile" action={!isAdmin && <Badge>Read only</Badge>}>
            {org ? (
              <OrgForm
                key={org.id + org.name + org.currency + org.country}
                initial={org}
                submitLabel="Save changes"
                disabled={!isAdmin}
                onSubmit={async (values) => {
                  await api("/organizations/current", { method: "PATCH", body: values });
                  setNotice("Organization updated.");
                  await Promise.all([refresh(), reload()]);
                }}
              />
            ) : (
              <div className="h-48 animate-pulse rounded bg-background" />
            )}
          </Card>

          <Card title="Users" action={members && <span className="text-xs text-muted">{members.length} total</span>}>
            {isAdmin && (
              <form onSubmit={addMember} className="mb-5 flex flex-wrap gap-2">
                <Input name="email" type="email" required placeholder="colleague@company.com" className="min-w-56 flex-1" aria-label="Email" />
                <Select name="role" defaultValue="viewer" className="w-32" aria-label="Role">
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {ROLE_LABEL[r]}
                    </option>
                  ))}
                </Select>
                <Button type="submit">Add user</Button>
                <p className="w-full text-xs text-muted">The person must have created a CostPilot account first.</p>
              </form>
            )}
            {!members ? (
              <div className="h-32 animate-pulse rounded bg-background" />
            ) : members.length === 0 ? (
              <EmptyState title="No members" />
            ) : (
              <div className="-mx-5 overflow-x-auto">
                <table className="w-full min-w-[520px] text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted">
                      <th className="px-5 py-2 font-medium">User</th>
                      <th className="px-3 py-2 font-medium">Role</th>
                      <th className="px-3 py-2 font-medium">Joined</th>
                      {isAdmin && <th className="px-5 py-2" />}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {members.map((m) => {
                      const self = m.user_id === me.user.id;
                      return (
                        <tr key={m.membership_id}>
                          <td className="px-5 py-2.5">
                            {m.email}
                            {self && <span className="ml-1.5 text-xs text-muted">(you)</span>}
                          </td>
                          <td className="px-3 py-2.5">
                            {isAdmin ? (
                              <Select
                                aria-label={`Role for ${m.email}`}
                                value={m.role}
                                className="h-8 w-28"
                                onChange={(e) =>
                                  run(
                                    () =>
                                      api(`/organizations/current/members/${m.membership_id}`, {
                                        method: "PATCH",
                                        body: { role: e.target.value },
                                      }).then(() => (self ? reload() : undefined)),
                                    "Role updated.",
                                  )
                                }
                              >
                                {ROLES.map((r) => (
                                  <option key={r} value={r}>
                                    {ROLE_LABEL[r]}
                                  </option>
                                ))}
                              </Select>
                            ) : (
                              <Badge tone={m.role === "admin" ? "accent" : "neutral"}>{ROLE_LABEL[m.role]}</Badge>
                            )}
                          </td>
                          <td className="px-3 py-2.5 text-muted">{new Date(m.joined_at).toLocaleDateString("en-GB")}</td>
                          {isAdmin && (
                            <td className="px-5 py-2.5 text-right">
                              {!self && (
                                <Button
                                  variant="danger"
                                  className="h-8"
                                  onClick={() => {
                                    if (window.confirm(`Remove ${m.email} from ${current.organization_name}?`)) {
                                      void run(
                                        () => api(`/organizations/current/members/${m.membership_id}`, { method: "DELETE" }),
                                        "Member removed.",
                                      );
                                    }
                                  }}
                                >
                                  Remove
                                </Button>
                              )}
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>

        <Card title="Commodity, alerts and data preferences">
          <EmptyState title="Configured in later sprints">
            Product specifications and data preferences (Sprint 2) · Alert thresholds (Sprint 4)
          </EmptyState>
        </Card>
      </div>
    </>
  );
}
