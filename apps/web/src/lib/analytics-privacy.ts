/** Only explicit application metadata crosses the browser analytics boundary. */
export const analyticsEvents = new Set([
  "planner_opened", "planner_message_submitted", "planner_details_edited",
  "planner_retry_requested", "planner_more_options_requested", "planner_results_viewed",
  "planner_stop_requested", "planner_left_during_turn", "planner_error", "$exception",
]);
const fields = new Set([
  "distinct_id", "planning_session_id", "turn_id", "$ai_trace_id", "$ai_session_id",
  "environment", "service", "stage", "error_code", "error_type", "edited_fields",
  "offer_count", "category_count", "outcome", "revision", "http_status", "reason",
  "$lib", "$lib_version",
]);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function isAnalyticsId(value: unknown): value is string {
  return typeof value === "string" && uuid.test(value);
}
function scalar(value: unknown): unknown {
  if (typeof value === "boolean" || (typeof value === "number" && Number.isFinite(value))) return value;
  if (typeof value === "string" && /^[\w .:/-]{0,100}$/.test(value) && !/(sk-|ph[cx]_|ghp_|github_pat_|:\/\/|@)/.test(value)) return value;
  if (Array.isArray(value)) return value.slice(0, 20).map(scalar).filter((item) => item !== undefined);
}
export function filterAnalyticsEvent<T extends { event: string; uuid: string; timestamp?: Date; properties: Record<string, unknown> }>(event: T): T | null {
  try {
    if (!analyticsEvents.has(event.event) || !isAnalyticsId(event.properties.planning_session_id)) return null;
    const properties: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(event.properties)) {
      if (fields.has(key)) {
        const safe = scalar(value);
        if (safe !== undefined) properties[key] = safe;
      }
    }
    properties.distinct_id = properties.planning_session_id;
    // The public project ingestion key is required by PostHog's event protocol.
    // It is configuration, distinct from any application session/auth token.
    if (typeof event.properties.token === "string" && /^phc_[A-Za-z0-9_-]+$/.test(event.properties.token)) {
      properties.token = event.properties.token;
    }
    properties.$process_person_profile = false;
    properties.$geoip_disable = true;
    if (event.event === "$exception") {
      properties.$exception_list = [{ type: properties.error_type ?? "ApplicationError", value: properties.error_code ?? "client_error" }];
    }
    return { event: event.event, uuid: event.uuid, timestamp: event.timestamp, properties } as T;
  } catch { return null; }
}
