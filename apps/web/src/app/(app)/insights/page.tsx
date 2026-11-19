import { ComingSoon } from "@/components/coming-soon";

export const metadata = { title: "AI Insights" };

export default function InsightsPage() {
  return (
    <ComingSoon
      title="AI Insights"
      description="Explanations generated only from CostPilot's own data and results, with sources."
      sprint={4}
      features={["Market summary", "Procurement Q&A", "Risk analysis", "Monthly report"]}
    />
  );
}
