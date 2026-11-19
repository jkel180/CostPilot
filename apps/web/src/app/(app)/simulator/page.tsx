import { ComingSoon } from "@/components/coming-soon";

export const metadata = { title: "Cost Simulator" };

export default function SimulatorPage() {
  return (
    <ComingSoon
      title="Cost Simulator"
      description="Translate price scenarios into expected expenditure for your volumes."
      sprint={3}
      features={["Expected expenditure", "Additional cost", "Potential savings", "Scenario comparison"]}
    />
  );
}
