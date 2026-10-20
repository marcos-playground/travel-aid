/**
 * Application-owned shapes for flight and hotel recommendations. They mirror what the
 * MVP needs to show; provider responses are mapped into them on the backend.
 *
 * Every amount is in US dollars and already covers the trip: all travelers for flights,
 * the full stay in one room for hotels.
 */

export type Category = "budget" | "mid-range" | "luxury";

export const CATEGORIES: Record<Category, { label: string; objective: string }> = {
  budget: { label: "Budget", objective: "Lowest-cost suitable options" },
  "mid-range": { label: "Mid-range", objective: "Balance of price, convenience and comfort" },
  luxury: { label: "Luxury", objective: "Most comfort, best location, cost shown clearly" },
};

export type FlightLeg = {
  /** Local date and time at the departure airport, `YYYY-MM-DDTHH:mm`. */
  departsAt: string;
  /** Local date and time at the arrival airport, `YYYY-MM-DDTHH:mm`. */
  arrivesAt: string;
  durationMinutes: number;
  /** Airport codes of each layover, empty for nonstop. */
  layovers: string[];
};

export type FlightOffer = {
  id: string;
  category: Category;
  airline: string;
  originAirport: string;
  destinationAirport: string;
  outbound: FlightLeg;
  inbound: FlightLeg;
  cabin: string;
  /** Baggage included in the fare, or null when the provider didn't say. */
  baggage: string | null;
  travelers: number;
  totalUsd: number;
};

export type HotelOffer = {
  id: string;
  category: Category;
  name: string;
  area: string;
  /** Where it sits relative to a landmark, such as "0.4 km to Puerta del Sol". */
  locationNote: string | null;
  rating: { value: number; scale: number; reviewCount: number | null; source: string } | null;
  /** Cancellation terms, or null when the provider didn't say. */
  cancellation: string | null;
  nights: number;
  rooms: number;
  totalUsd: number;
  /** False when the price excludes taxes and fees; null when unknown. */
  taxesIncluded: boolean | null;
};

/** One flight and one hotel per category, either of which may be missing. */
export type Recommendation = {
  category: Category;
  flight: FlightOffer | null;
  hotel: HotelOffer | null;
  /** The assistant's explanation of the tradeoffs, grounded in the offers. */
  rationale: string;
};

export type RecommendationSet = {
  recommendations: Recommendation[];
  /** When the prices were retrieved, as an ISO timestamp. */
  retrievedAt: string;
  sources: string[];
  /** Sample or test data must be labeled as such wherever it is shown. */
  isSample: boolean;
};

export function flightOffers(set: RecommendationSet): FlightOffer[] {
  return set.recommendations.flatMap((recommendation) => (recommendation.flight ? [recommendation.flight] : []));
}

export function hotelOffers(set: RecommendationSet): HotelOffer[] {
  return set.recommendations.flatMap((recommendation) => (recommendation.hotel ? [recommendation.hotel] : []));
}

export type Combination = { flight: FlightOffer; hotel: HotelOffer };

export function combinationTotal({ flight, hotel }: Combination): number {
  return flight.totalUsd + hotel.totalUsd;
}

/**
 * Single swaps (change the flight or change the hotel) that bring an over-budget
 * combination within budget, most comfortable first: the highest total that still fits.
 */
export function swapsWithinBudget(
  current: Combination,
  flights: FlightOffer[],
  hotels: HotelOffer[],
  budgetUsd: number,
  limit = 2,
): Combination[] {
  const swaps = [
    ...flights.filter((flight) => flight.id !== current.flight.id).map((flight) => ({ flight, hotel: current.hotel })),
    ...hotels.filter((hotel) => hotel.id !== current.hotel.id).map((hotel) => ({ flight: current.flight, hotel })),
  ];
  return swaps
    .filter((swap) => combinationTotal(swap) <= budgetUsd)
    .sort((a, b) => combinationTotal(b) - combinationTotal(a))
    .slice(0, limit);
}
