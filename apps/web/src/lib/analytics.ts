"use client";

import posthog, { type PostHog } from "posthog-js";
import { filterAnalyticsEvent, isAnalyticsId } from "./analytics-privacy";

let sdk: PostHog | undefined;
let sessionId: string | undefined;
const enabled = process.env.NEXT_PUBLIC_POSTHOG_ENABLED === "true";
const environment = process.env.NEXT_PUBLIC_POSTHOG_ENVIRONMENT ?? "development";

/** Initialize only after the server supplies a public, plan-specific random ID. */
export function startAnalytics(id: string) {
  if (!enabled || !isAnalyticsId(id) || !process.env.NEXT_PUBLIC_POSTHOG_KEY || !process.env.NEXT_PUBLIC_POSTHOG_HOST) return;
  try {
    if (sessionId === id && sdk) return;
    if (sdk) {
      sdk.reset({ bootstrap: { distinctID: id, isIdentifiedID: false } });
    } else {
      sdk = posthog.init(process.env.NEXT_PUBLIC_POSTHOG_KEY, {
        api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST,
        bootstrap: { distinctID: id, isIdentifiedID: false },
        persistence: "memory", disable_persistence: true, person_profiles: "never",
        autocapture: false, capture_pageview: false, capture_pageleave: false,
        capture_exceptions: false, capture_performance: false,
        disable_session_recording: true, disable_surveys: true, disable_product_tours: true,
        disable_external_dependency_loading: true, advanced_disable_feature_flags: true,
        advanced_disable_feature_flags_on_first_load: true, remote_config_refresh_interval_ms: 0,
        before_send: filterAnalyticsEvent,
      }, "travel-aid");
    }
    sessionId = id;
  } catch { /* Analytics must never stop planning. */ }
}

export function track(event: string, properties: Record<string, unknown> = {}, leaving = false) {
  try {
    if (!sdk || !sessionId) return;
    const metadata = {
      ...properties, planning_session_id: sessionId, $ai_session_id: sessionId,
      environment, service: "web", $process_person_profile: false, $geoip_disable: true,
    };
    if (event === "$exception") {
      sdk.captureException(new Error(String(properties.error_code ?? "client_error")), metadata);
    } else {
      sdk.capture(event, metadata, leaving ? { transport: "sendBeacon", send_instantly: true } : undefined);
    }
  } catch { /* Best-effort capture. */ }
}

export function trackError(code: string, stage: string, turnId?: string) {
  const properties = { error_code: code, stage, error_type: "ClientPlanningError",
    ...(turnId ? { turn_id: turnId, $ai_trace_id: turnId } : {}) };
  track("planner_error", properties);
  // Static error codes only. No exception message, source, URL, or browser state.
  track("$exception", properties);
}
