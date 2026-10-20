"use client";

import { format } from "date-fns";
import { cn } from "@/lib/utils";
import { parseTripDate } from "../trip";
import { useTrip } from "../trip-provider";

/** A postmark that stamps the destination and departure date once they're set. Decorative. */
export function TripPostmark({ className }: { className?: string }) {
  const { trip } = useTrip();
  const departure = trip.departureDate ? parseTripDate(trip.departureDate) : null;
  const place = trip.destination ?? "Anywhere";

  return (
    <div
      aria-hidden
      className={cn(
        "postmark relative grid size-24 shrink-0 -rotate-12 place-items-center rounded-full border-3 border-white/85 text-center font-mono text-[9px] leading-normal font-bold tracking-[0.12em] text-white sm:size-32 sm:text-[11px]",
        className,
      )}
    >
      <span className="flex max-w-[80%] flex-col items-center">
        <span>{trip.origin ? "ROUND TRIP" : "TRAVEL AID"}</span>
        <span
          className={cn(
            "max-w-full truncate font-heading font-extrabold tracking-normal uppercase",
            // Long names get a smaller stamp so more of them fits inside the circle.
            place.length > 7 ? "text-xs sm:text-sm" : "text-base sm:text-xl",
          )}
        >
          {place}
        </span>
        <span>{departure ? format(departure, "MMM d · yyyy").toUpperCase() : "YOUR NEXT TRIP"}</span>
      </span>
    </div>
  );
}
