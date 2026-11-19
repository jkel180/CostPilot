import { ComingSoon } from "@/components/coming-soon";

export const metadata = { title: "My Purchases" };

export default function PurchasesPage() {
  return (
    <ComingSoon
      title="My Purchases"
      description="Your purchase history, compared with market benchmarks of the same specification."
      sprint={2}
      features={["CSV upload with column mapping", "Purchase history", "Supplier analysis", "Price evolution", "Product specifications"]}
    />
  );
}
