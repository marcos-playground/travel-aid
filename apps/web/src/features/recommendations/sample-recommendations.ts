import type { Trip } from "@/features/trip/trip";
import type { RecommendationSet } from "./recommendations";

/** The MVP example journey: Santo Domingo to Madrid, Feb 10–15, 2027, one traveler, $2,000. */
export const SAMPLE_TRIP: Trip = {
  origin: "Santo Domingo",
  destination: "Madrid",
  departureDate: "2027-02-10",
  returnDate: "2027-02-15",
  travelers: 1,
  budgetUsd: 2000,
  flightBudgetUsd: null,
};

/**
 * Made-up offers for the sample trip, used to build and review the results UI before the
 * search integration exists. Always shown with a "Sample data" label.
 */
export const SAMPLE_RECOMMENDATIONS: RecommendationSet = {
  isSample: true,
  retrievedAt: "2026-10-20T21:14:00-04:00",
  sources: ["Google Flights", "Google Hotels"],
  recommendations: [
    {
      category: "budget",
      rationale: "Cheapest pair with a workable connection and good reviews. The Miami layover adds about 4½ hours each way.",
      flight: {
        id: "sample-flight-budget",
        category: "budget",
        airline: "Airline A",
        originAirport: "SDQ",
        destinationAirport: "MAD",
        outbound: { departsAt: "2027-02-10T15:10", arrivesAt: "2027-02-11T09:25", durationMinutes: 795, layovers: ["MIA"] },
        inbound: { departsAt: "2027-02-15T11:40", arrivesAt: "2027-02-15T19:25", durationMinutes: 765, layovers: ["MIA"] },
        cabin: "Economy",
        baggage: "Carry-on only",
        travelers: 1,
        totalUsd: 780,
      },
      hotel: {
        id: "sample-hotel-budget",
        category: "budget",
        name: "3★ guesthouse in Lavapiés",
        area: "Lavapiés",
        locationNote: "1.2 km to Puerta del Sol",
        rating: { value: 4.2, scale: 5, reviewCount: 860, source: "Google reviews" },
        cancellation: "Free cancellation until Feb 8",
        nights: 5,
        rooms: 1,
        totalUsd: 410,
        taxesIncluded: false,
      },
    },
    {
      category: "mid-range",
      rationale: "Nonstop both ways and a central 4★ hotel, for $470 more than Budget. Still leaves room in your budget.",
      flight: {
        id: "sample-flight-mid",
        category: "mid-range",
        airline: "Airline B",
        originAirport: "SDQ",
        destinationAirport: "MAD",
        outbound: { departsAt: "2027-02-10T20:30", arrivesAt: "2027-02-11T10:05", durationMinutes: 515, layovers: [] },
        inbound: { departsAt: "2027-02-15T15:15", arrivesAt: "2027-02-15T19:55", durationMinutes: 580, layovers: [] },
        cabin: "Economy",
        baggage: "1 checked bag",
        travelers: 1,
        totalUsd: 940,
      },
      hotel: {
        id: "sample-hotel-mid",
        category: "mid-range",
        name: "4★ hotel near Gran Vía",
        area: "Gran Vía",
        locationNote: "0.4 km to Puerta del Sol",
        rating: { value: 4.5, scale: 5, reviewCount: 2140, source: "Google reviews" },
        cancellation: "Free cancellation until Feb 9",
        nights: 5,
        rooms: 1,
        totalUsd: 720,
        taxesIncluded: true,
      },
    },
    {
      category: "luxury",
      rationale: "Premium economy and a 5★ hotel in quiet, upscale Salamanca. Goes $470 over your budget.",
      flight: {
        id: "sample-flight-luxury",
        category: "luxury",
        airline: "Airline B",
        originAirport: "SDQ",
        destinationAirport: "MAD",
        outbound: { departsAt: "2027-02-10T20:30", arrivesAt: "2027-02-11T10:05", durationMinutes: 515, layovers: [] },
        inbound: { departsAt: "2027-02-15T15:15", arrivesAt: "2027-02-15T19:55", durationMinutes: 580, layovers: [] },
        cabin: "Premium economy",
        baggage: "2 checked bags",
        travelers: 1,
        totalUsd: 1320,
      },
      hotel: {
        id: "sample-hotel-luxury",
        category: "luxury",
        name: "5★ hotel in Salamanca",
        area: "Salamanca",
        locationNote: "2.1 km to Puerta del Sol",
        rating: { value: 4.7, scale: 5, reviewCount: 1310, source: "Google reviews" },
        cancellation: "Non-refundable",
        nights: 5,
        rooms: 1,
        totalUsd: 1150,
        taxesIncluded: true,
      },
    },
  ],
};
