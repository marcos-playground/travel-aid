import assert from "node:assert/strict";
import { test } from "node:test";
import { createPlanningEdits } from "../src/features/planner/planning-edits.ts";

test("an edit survives turn.failed then turn.completed and is sent on retry", () => {
  const edits = createPlanningEdits();
  edits.queue({ flightBudgetUsd: 900 });
  assert.deepEqual(edits.submit(), { flightBudgetUsd: 900 });
  edits.recover(); // turn.failed before trip.updated
  edits.recover(); // turn.completed is only a terminal snapshot
  assert.deepEqual(edits.snapshot(), { flightBudgetUsd: 900 });
  assert.equal(edits.isDirty(), true);
  assert.deepEqual(edits.submit(), { flightBudgetUsd: 900 });
  edits.accept(); // trip.updated after explicit retry
  assert.equal(edits.isDirty(), false);
});

test("newer edits win over an older failed submission, including clearing a field", () => {
  const edits = createPlanningEdits();
  edits.queue({ destination: "JFK", flightBudgetUsd: 900 });
  edits.submit();
  edits.queue({ destination: "MAD", flightBudgetUsd: null });
  edits.recover();
  assert.deepEqual(edits.submit(), { destination: "MAD", flightBudgetUsd: null });
});

test("an edit made during a rejected turn still sends on its own", () => {
  const edits = createPlanningEdits();
  edits.queue({ destination: "JFK" });
  edits.submit();
  edits.queue({ flightBudgetUsd: 900 }); // edited while the turn runs
  edits.recover(); // turn.completed without trip.updated
  assert.equal(edits.hasNewEdits(), true);
  assert.deepEqual(edits.submit(), { destination: "JFK", flightBudgetUsd: 900 });
  assert.equal(edits.hasNewEdits(), false);
});

test("a recovered edit alone waits for the next turn instead of resending", () => {
  const edits = createPlanningEdits();
  edits.queue({ flightBudgetUsd: 900 });
  edits.submit();
  edits.recover(); // turn.completed without trip.updated
  assert.equal(edits.hasNewEdits(), false);
  assert.equal(edits.isDirty(), true);
});

test("accepted edits are not replayed after a later stream/provider failure", () => {
  const edits = createPlanningEdits();
  edits.queue({ origin: "SDQ", flightBudgetUsd: 900 });
  edits.submit();
  edits.accept(); // trip.updated
  edits.queue({ flightBudgetUsd: 1000 });
  edits.recover(); // stream/provider fails after the server accepted the old edit
  assert.deepEqual(edits.submit(), { flightBudgetUsd: 1000 });
});
