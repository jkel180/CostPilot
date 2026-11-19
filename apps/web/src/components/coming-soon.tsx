import { PageHeader } from "@/components/app-shell";
import { Card, EmptyState } from "@/components/ui";

export function ComingSoon({
  title,
  description,
  sprint,
  features,
}: {
  title: string;
  description: string;
  sprint: number;
  features: string[];
}) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <Card>
        <EmptyState title={`Planned for Sprint ${sprint}`}>{features.join(" · ")}</EmptyState>
      </Card>
    </>
  );
}
