import { ComingSoon } from "@/components/coming-soon";

export const metadata = { title: "Forecasting" };

export default function ForecastingPage() {
  return (
    <ComingSoon
      title="Forecasting"
      description="1, 3 and 6-month forecasts with prediction intervals, backtested against simple baselines."
      sprint={3}
      features={["Forecast charts", "Prediction intervals", "Scenario comparison", "Model performance", "Generation date"]}
    />
  );
}
