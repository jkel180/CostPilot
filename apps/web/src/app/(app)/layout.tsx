import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { OrgProvider } from "@/components/org-context";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <OrgProvider>
      <AppShell>{children}</AppShell>
    </OrgProvider>
  );
}
