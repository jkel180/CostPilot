import { ComingSoon } from "@/components/coming-soon";

export const metadata = { title: "Market Intelligence" };

export default function MarketPage() {
  return (
    <ComingSoon
      title="Market Intelligence"
      description="Lemon juice concentrate benchmarks, trade flows and market drivers."
      sprint={2}
      features={["Price history", "Market drivers", "Geographic breakdown", "Trade statistics", "Source information"]}
    />
  );
}
