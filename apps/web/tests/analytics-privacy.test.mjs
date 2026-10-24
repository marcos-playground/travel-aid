import assert from "node:assert/strict";
import { test } from "node:test";
import { filterAnalyticsEvent } from "../src/lib/analytics-privacy.ts";

const id = "aadbb674-69cb-47b3-a07d-6e708ff5127c";
test("analytics boundary strips browser enrichment, content and persistent identities", () => {
  const result = filterAnalyticsEvent({ event: "planner_message_submitted", uuid: id,
    $set: { email: "secret@example.com" }, properties: {
      planning_session_id: id, distinct_id: "persistent-device", $device_id: "persistent-device",
      $session_id: "browser-session", $current_url: "https://example.com/?token=secret",
      text: "Private trip description", turn_id: id, edited_fields: ["origin", "travelers"],
      service: "web", environment: "development",
      token: "phc_public_ingestion_key",
    } });
  assert.equal(result.properties.distinct_id, id);
  assert.equal(result.properties.$process_person_profile, false);
  assert.equal(result.properties.$geoip_disable, true);
  assert.equal(result.properties.token, "phc_public_ingestion_key");
  assert.deepEqual(result.properties.edited_fields, ["origin", "travelers"]);
  assert.ok(!JSON.stringify(result).includes("secret"));
  assert.ok(!JSON.stringify(result).includes("Private"));
  assert.ok(!JSON.stringify(result).includes("persistent-device"));
  assert.ok(!("$session_id" in result.properties));
});
test("only explicit events with public UUID identities pass", () => {
  assert.equal(filterAnalyticsEvent({ event: "$autocapture", uuid: id, properties: { planning_session_id: id } }), null);
  assert.equal(filterAnalyticsEvent({ event: "planner_opened", uuid: id, properties: { planning_session_id: "cookie-hash" } }), null);
  assert.equal(filterAnalyticsEvent({ event: "planner_opened", uuid: id, properties: null }), null);
});
test("native errors carry a static code, with no raw exception or stack", () => {
  const result = filterAnalyticsEvent({ event: "$exception", uuid: id, properties: {
    planning_session_id: id, error_code: "turn_request_failed", error_type: "ClientPlanningError",
    $exception_list: [{ value: "private trip", stacktrace: "secret" }],
  } });
  assert.deepEqual(result.properties.$exception_list, [{ type: "ClientPlanningError", value: "turn_request_failed" }]);
  assert.ok(!JSON.stringify(result).includes("secret"));
});
