import { differenceInCalendarDays, format, parseISO } from "date-fns";
import type { FlightLeg, FlightOffer, HotelOffer } from "./recommendations";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

/** "$1,660". Negative amounts are shown without a sign; callers say "over" or "left". */
export function formatAmount(amount: number): string {
  return usd.format(Math.abs(amount));
}

/** "13h 15m" */
export function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

/** "15:10 → 09:25 +1" */
export function formatLegTimes(leg: FlightLeg): string {
  const departs = parseISO(leg.departsAt);
  const arrives = parseISO(leg.arrivesAt);
  const dayShift = differenceInCalendarDays(arrives, departs);
  return `${format(departs, "HH:mm")} → ${format(arrives, "HH:mm")}${dayShift > 0 ? ` +${dayShift}` : ""}`;
}

/** "SDQ → MIA → MAD" */
export function formatRoute(flight: FlightOffer): string {
  return [flight.originAirport, ...flight.outbound.layovers, flight.destinationAirport].join(" → ");
}

export function formatStops(leg: FlightLeg): string {
  if (leg.layovers.length === 0) return "Nonstop";
  return `${leg.layovers.length} ${leg.layovers.length === 1 ? "stop" : "stops"} via ${leg.layovers.join(", ")}`;
}

/** "★ 4.2/5 (860 Google reviews)" */
export function formatRating({ value, scale, reviewCount, source }: NonNullable<HotelOffer["rating"]>): string {
  const count = reviewCount === null ? "" : `${reviewCount.toLocaleString("en-US")} `;
  return `★ ${value}/${scale} (${count}${source})`;
}
