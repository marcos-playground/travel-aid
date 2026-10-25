import assert from "node:assert/strict";
import { test } from "node:test";
import { readPlanningStream } from "../src/features/planner/stream.ts";

test("SSE decoding survives every byte split, CRLF and multibyte text", async () => {
  const bytes = new TextEncoder().encode(': ping\r\n\r\nevent: trip.updated\r\ndata: {"text":"Madrid → SDQ"}\r\n\r\ndata: {"type":"done"}\n\n');
  const values = [];
  const stream = new ReadableStream({ start(controller) {
    for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
    controller.close();
  } });
  await readPlanningStream(stream, (value) => values.push(value));
  assert.deepEqual(values, [{ text: "Madrid → SDQ" }, { type: "done" }]);
});
