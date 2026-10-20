import { startOfToday } from "date-fns";
import { EMPTY_TRIP, type Trip, type TripErrors, type TripField, type TripPatch, validateTrip } from "./trip";

export type TripUpdateResult = { ok: true; trip: Trip } | { ok: false; trip: Trip; errors: TripErrors };

/**
 * Holds the trip being planned. The trip strip, the chat and WebMCP tools all write through
 * `update`, so every change gets the same validation and nothing half-applies.
 */
export function createTripStore(initial: Trip = EMPTY_TRIP) {
  let trip = initial;
  const listeners = new Set<() => void>();

  return {
    getSnapshot: () => trip,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    update(patch: TripPatch): TripUpdateResult {
      const changed = (Object.keys(patch) as TripField[]).filter((field) => patch[field] !== undefined);
      const next: Trip = { ...trip };
      for (const field of changed) {
        const value = patch[field];
        (next as Record<TripField, unknown>)[field] = typeof value === "string" ? value.trim() : value;
      }
      const errors = validateTrip(next, { today: startOfToday(), changed });
      if (Object.keys(errors).length > 0) return { ok: false, trip, errors };

      trip = next;
      listeners.forEach((listener) => listener());
      return { ok: true, trip };
    },
  };
}

export type TripStore = ReturnType<typeof createTripStore>;
