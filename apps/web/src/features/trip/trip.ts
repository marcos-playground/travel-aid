import { differenceInCalendarDays, format, isValid, parse } from "date-fns";

/**
 * The details the first flight and hotel search needs. The MVP always books one hotel
 * room, round trip, in USD, so those are constants rather than fields.
 *
 * Dates are calendar dates in `YYYY-MM-DD` form, with no time zone.
 */
export type Trip = {
  origin: string | null;
  destination: string | null;
  departureDate: string | null;
  returnDate: string | null;
  travelers: number | null;
  budgetUsd: number | null;
};

export type TripField = keyof Trip;
export type TripPatch = Partial<Trip>;
export type TripErrors = Partial<Record<TripField, string>>;

export const EMPTY_TRIP: Trip = {
  origin: null,
  destination: null,
  departureDate: null,
  returnDate: null,
  travelers: null,
  budgetUsd: null,
};

export const ROOMS = 1;
export const MAX_TRAVELERS = 9;
export const MAX_BUDGET_USD = 1_000_000;
const MAX_PLACE_LENGTH = 100;
const ISO_DATE = "yyyy-MM-dd";

/**
 * One description per field, shared by the trip strip and the WebMCP tool schema so
 * people and agents are told the same thing.
 */
export const TRIP_FIELDS: Record<TripField, { label: string; description: string }> = {
  origin: {
    label: "From",
    description: "City or airport the trip leaves from, such as 'Santo Domingo' or 'SDQ'.",
  },
  destination: {
    label: "To",
    description: "The one city or airport the trip goes to, such as 'Madrid' or 'MAD'.",
  },
  departureDate: {
    label: "Depart",
    description: "Outbound flight date and hotel check-in date, as YYYY-MM-DD. Today or later.",
  },
  returnDate: {
    label: "Return",
    description: "Return flight date and hotel check-out date, as YYYY-MM-DD. After the departure date.",
  },
  travelers: {
    label: "Travelers",
    description: `Number of people traveling, from 1 to ${MAX_TRAVELERS}. They share one hotel room.`,
  },
  budgetUsd: {
    label: "Budget",
    description: "Total budget in US dollars for round-trip flights for everyone plus the full hotel stay.",
  },
};

export const TRIP_FIELD_ORDER: TripField[] = [
  "origin",
  "destination",
  "departureDate",
  "returnDate",
  "travelers",
  "budgetUsd",
];

export function parseTripDate(value: string): Date | null {
  const date = parse(value, ISO_DATE, new Date(0));
  return isValid(date) && format(date, ISO_DATE) === value ? date : null;
}

export function toTripDate(date: Date): string {
  return format(date, ISO_DATE);
}

export function missingFields(trip: Trip): TripField[] {
  return TRIP_FIELD_ORDER.filter((field) => trip[field] === null);
}

/**
 * Checks a whole trip. Existing values are trusted to have been valid when they were set,
 * so "not in the past" only applies to the dates in `changed`.
 */
export function validateTrip(
  trip: Trip,
  { today, changed }: { today: Date; changed: TripField[] },
): TripErrors {
  const errors: TripErrors = {};

  for (const field of ["origin", "destination"] as const) {
    const value = trip[field];
    if (value === null) continue;
    if (!value.trim()) errors[field] = "Enter a city or airport.";
    else if (value.length > MAX_PLACE_LENGTH) errors[field] = "Use 100 characters or fewer.";
  }
  if (
    !errors.destination &&
    trip.origin !== null &&
    trip.destination !== null &&
    trip.origin.trim().toLowerCase() === trip.destination.trim().toLowerCase()
  ) {
    errors.destination = "Choose a destination different from where you're leaving.";
  }

  const departure = trip.departureDate === null ? null : parseTripDate(trip.departureDate);
  const ret = trip.returnDate === null ? null : parseTripDate(trip.returnDate);
  if (trip.departureDate !== null && !departure) errors.departureDate = "Use a real date in YYYY-MM-DD form.";
  if (trip.returnDate !== null && !ret) errors.returnDate = "Use a real date in YYYY-MM-DD form.";
  if (departure && changed.includes("departureDate") && differenceInCalendarDays(departure, today) < 0) {
    errors.departureDate = "Choose today or a later date.";
  }
  if (departure && ret && differenceInCalendarDays(ret, departure) < 1) {
    errors.returnDate = "Choose a return date after the departure date.";
  }

  if (trip.travelers !== null && (!Number.isInteger(trip.travelers) || trip.travelers < 1 || trip.travelers > MAX_TRAVELERS)) {
    errors.travelers = `Choose between 1 and ${MAX_TRAVELERS} travelers.`;
  }
  if (trip.budgetUsd !== null && (!Number.isFinite(trip.budgetUsd) || trip.budgetUsd <= 0 || trip.budgetUsd > MAX_BUDGET_USD)) {
    errors.budgetUsd = "Enter a budget above $0.";
  }

  return errors;
}

export function nights(trip: Trip): number | null {
  if (!trip.departureDate || !trip.returnDate) return null;
  const departure = parseTripDate(trip.departureDate);
  const ret = parseTripDate(trip.returnDate);
  return departure && ret ? differenceInCalendarDays(ret, departure) : null;
}

/** "Feb 10 – 15, 2027", "Feb 27 – Mar 3, 2027" or "Dec 28, 2026 – Jan 2, 2027". */
export function formatDateRange(trip: Trip): string | null {
  const departure = trip.departureDate ? parseTripDate(trip.departureDate) : null;
  const ret = trip.returnDate ? parseTripDate(trip.returnDate) : null;
  if (!departure) return null;
  if (!ret) return `${format(departure, "MMM d, yyyy")} – ?`;
  if (departure.getFullYear() !== ret.getFullYear()) {
    return `${format(departure, "MMM d, yyyy")} – ${format(ret, "MMM d, yyyy")}`;
  }
  if (departure.getMonth() !== ret.getMonth()) {
    return `${format(departure, "MMM d")} – ${format(ret, "MMM d, yyyy")}`;
  }
  return `${format(departure, "MMM d")} – ${format(ret, "d, yyyy")}`;
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export function formatUsd(amount: number): string {
  return `${usd.format(amount)} USD`;
}
