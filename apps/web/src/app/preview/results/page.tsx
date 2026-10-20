import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PlannerPage } from "@/features/planner/components/planner-page";
import { SAMPLE_RECOMMENDATIONS, SAMPLE_TRIP } from "@/features/recommendations/sample-recommendations";

export const metadata: Metadata = {
  title: "Results preview · Travel Aid",
  robots: { index: false },
};

/**
 * The planner after a completed search, filled with labeled sample data so the results UI
 * can be reviewed before the assistant and search are connected. Hidden in production.
 */
export default function ResultsPreview() {
  if (process.env.VERCEL_ENV === "production") notFound();

  return (
    <PlannerPage
      initialTrip={SAMPLE_TRIP}
      initialMessages={[
        {
          id: "sample-request",
          role: "user",
          text: "Santo Domingo to Madrid, Feb 10 to 15, 2027. Just me, $2,000 for flights and the hotel.",
        },
        {
          id: "sample-results",
          role: "assistant",
          text: "I found a Budget, Mid-range and Luxury pair, but you can mix them: pick any flight and any hotel and I'll keep the total in check.",
          recommendations: SAMPLE_RECOMMENDATIONS,
        },
      ]}
    />
  );
}
