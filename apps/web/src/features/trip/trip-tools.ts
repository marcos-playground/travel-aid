import type { WebMcpTool } from "@/lib/webmcp";
import {
  MAX_BUDGET_USD,
  MAX_TRAVELERS,
  ROOMS,
  TRIP_FIELDS,
  TRIP_FIELD_ORDER,
  missingFields,
  type Trip,
  type TripField,
  type TripPatch,
} from "./trip";
import type { TripStore } from "./trip-store";

const nullable = (schema: Record<string, unknown>, field: TripField) => ({
  ...schema,
  type: [schema.type, "null"],
  description: TRIP_FIELDS[field].description,
});

const TRIP_PROPERTIES: Record<TripField, Record<string, unknown>> = {
  origin: nullable({ type: "string", minLength: 1, maxLength: 100 }, "origin"),
  destination: nullable({ type: "string", minLength: 1, maxLength: 100 }, "destination"),
  departureDate: nullable({ type: "string", format: "date" }, "departureDate"),
  returnDate: nullable({ type: "string", format: "date" }, "returnDate"),
  travelers: nullable({ type: "integer", minimum: 1, maximum: MAX_TRAVELERS }, "travelers"),
  budgetUsd: nullable({ type: "number", exclusiveMinimum: 0, maximum: MAX_BUDGET_USD }, "budgetUsd"),
  flightBudgetUsd: nullable({ type: "number", exclusiveMinimum: 0, maximum: MAX_BUDGET_USD }, "flightBudgetUsd"),
};

/** What an agent needs to know to finish the trip: current values and what is still missing. */
function describeTrip(trip: Trip) {
  const missing = missingFields(trip);
  return {
    trip,
    fixed: { tripType: "round_trip", rooms: ROOMS, currency: "USD", adultsOnly: true },
    missingFields: missing.map((field) => ({ field, description: TRIP_FIELDS[field].description })),
    readyToSearch: missing.length === 0,
  };
}

function toPatch(input: Record<string, unknown>): { patch: TripPatch; unknown: string[] } {
  const patch: Record<string, unknown> = {};
  const unknown: string[] = [];
  for (const [key, value] of Object.entries(input)) {
    if ((TRIP_FIELD_ORDER as string[]).includes(key)) patch[key] = value;
    else unknown.push(key);
  }
  return { patch: patch as TripPatch, unknown };
}

function hasExpectedType(field: TripField, value: unknown) {
  if (value === null) return true;
  return field === "travelers" || field === "budgetUsd" || field === "flightBudgetUsd" ? typeof value === "number" : typeof value === "string";
}

/**
 * WebMCP tools for the trip strip. They read and write the same store as the page, so an
 * agent's changes show up in the strip and go through the same validation as a person's.
 */
export function createTripTools(store: TripStore): WebMcpTool[] {
  return [
    {
      name: "get_trip_details",
      title: "Get trip details",
      description:
        "Read the trip being planned: origin, destination, dates, travelers and budget. Lists the details still " +
        "missing before flights can be searched. Flights are round trip, adults only, in USD. Flight budget is optional; combined flight-and-hotel budget is separate.",
      inputSchema: { type: "object", properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: true },
      execute: () => describeTrip(store.getSnapshot()),
    },
    {
      name: "update_trip_details",
      title: "Update trip details",
      description:
        "Set or correct trip details shown in the trip summary. Send only the fields to change; null clears a " +
        "field. If any value is invalid, nothing changes and the errors say why. The response lists what is " +
        "still missing.",
      inputSchema: {
        type: "object",
        properties: TRIP_PROPERTIES,
        additionalProperties: false,
        minProperties: 1,
      },
      execute: (input) => {
        const { patch, unknown } = toPatch(input ?? {});
        if (unknown.length > 0) {
          return { ok: false, errors: { _: `Unknown fields: ${unknown.join(", ")}.` }, ...describeTrip(store.getSnapshot()) };
        }
        const wrongType = (Object.keys(patch) as TripField[]).filter((field) => !hasExpectedType(field, patch[field]));
        if (wrongType.length > 0) {
          const errors = Object.fromEntries(wrongType.map((field) => [field, "Wrong type. See the input schema."]));
          return { ok: false, errors, ...describeTrip(store.getSnapshot()) };
        }
        const result = store.update(patch);
        return result.ok
          ? { ok: true, ...describeTrip(result.trip) }
          : { ok: false, errors: result.errors, ...describeTrip(result.trip) };
      },
    },
  ];
}
