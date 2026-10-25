import type { TripPatch } from "../trip/trip";

/** Keep edits until the server accepts them, with newer local changes taking precedence. */
export function createPlanningEdits() {
  let pending: TripPatch = {};
  let submitted: TripPatch = {};
  // Recovered edits wait for the next turn; only edits made since the last submit send on their own.
  let edited = false;
  return {
    queue(patch: TripPatch) {
      pending = { ...pending, ...patch };
      edited = true;
    },
    submit() {
      const patch = pending;
      pending = {};
      submitted = patch;
      edited = false;
      return patch;
    },
    accept() {
      submitted = {};
    },
    recover() {
      pending = { ...submitted, ...pending };
      submitted = {};
    },
    snapshot: (): TripPatch => ({ ...submitted, ...pending }),
    hasNewEdits: () => edited,
    isDirty: () => Object.keys(pending).length > 0 || Object.keys(submitted).length > 0,
  };
}
