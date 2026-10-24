import type { TripPatch } from "../trip/trip";

/** Keep edits until the server accepts them, with newer local changes taking precedence. */
export function createPlanningEdits() {
  let pending: TripPatch = {};
  let submitted: TripPatch = {};
  return {
    queue(patch: TripPatch) {
      pending = { ...pending, ...patch };
    },
    submit() {
      const patch = pending;
      pending = {};
      submitted = patch;
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
    hasPending: () => Object.keys(pending).length > 0,
    isDirty: () => Object.keys(pending).length > 0 || Object.keys(submitted).length > 0,
  };
}
