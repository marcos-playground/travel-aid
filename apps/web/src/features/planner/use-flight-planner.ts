"use client";

import { useEffect, useRef, useState } from "react";
import type { PlanningEvent, Session } from "@travel-aid/api-client";
import { useTripStore } from "@/features/trip/trip-provider";
import { readPlanningStream } from "./stream";
import { createPlanningEdits } from "./planning-edits";
import { startAnalytics, track, trackError } from "@/lib/analytics";

type Operations = {
  send: (text: string, source?: "chat" | "more_options") => Promise<boolean>;
  retry: () => void;
  stop: () => void;
  select: (id: string) => Promise<void>;
};

async function requireResponse(response: Response) {
  if (response.ok) return response;
  const data = await response.json().catch(() => null);
  throw new Error(typeof data?.detail === "string" ? data.detail : "The request failed. Please try again.");
}

export function useFlightPlanner() {
  const store = useTripStore();
  const [session, setSession] = useState<Session | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const operations = useRef<Operations | null>(null);

  useEffect(() => {
    let disposed = false;
    let current: Session | null = null;
    const edits = createPlanningEdits();
    let running = false;
    let activeTurn: string | undefined;
    let viewedTurn: string | undefined;
    let openedSession: string | undefined;
    let controller: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const boot = new AbortController();

    function apply(next: Session) {
      if (disposed || (current && next.revision < current.revision)) return;
      current = next;
      startAnalytics(next.analyticsId);
      setSession(next);
      // Server hydration must not be mistaken for a manual edit. Edits made during
      // an in-flight turn stay visible and are sent next, rather than overwritten.
      store.replace({ ...next.trip, ...edits.snapshot() });
      setDirty(edits.isDirty());
    }

    async function restore() {
      const response = await requireResponse(await fetch("/api/planning/session", {
        method: "POST", signal: boot.signal, cache: "no-store",
      }));
      const next: Session = await response.json();
      apply(next);
      if (openedSession !== next.analyticsId) {
        openedSession = next.analyticsId;
        track("planner_opened", { revision: next.revision });
      }
      return next;
    }

    function scheduleEdits() {
      clearTimeout(timer);
      if (!disposed && !running && current && edits.hasNewEdits()) {
        timer = setTimeout(() => { void turn(""); }, 350);
      }
    }

    async function turn(text: string, retry = false, source: "chat" | "more_options" = "chat"): Promise<boolean> {
      if (disposed || running) return false;
      running = true;
      setBusy(true);
      setError(null);
      const patch = edits.submit();
      controller = new AbortController();
      const requestId = crypto.randomUUID();
      activeTurn = requestId;
      let completed = false;
      let failed = false;
      try {
        const snapshot = current ?? await restore();
        track(retry ? "planner_retry_requested" : source === "more_options" ? "planner_more_options_requested" : text.trim() ? "planner_message_submitted" : "planner_details_edited", {
          turn_id: requestId, $ai_trace_id: requestId, edited_fields: Object.keys(patch),
        });
        const response = await requireResponse(await fetch("/api/planning/messages", {
          method: "POST", headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({ text, patch, retry, requestId,
            expectedRevision: snapshot.revision,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC" }),
        }));
        if (!response.body) throw new Error("The response stream is unavailable. Please try again.");
        await readPlanningStream(response.body, (value) => {
          if (!value || typeof value !== "object" || !("type" in value) || !("session" in value)) return;
          const event = value as PlanningEvent;
          if (event.type === "trip.updated") edits.accept();
          // A terminal snapshot is not an acknowledgement of submitted edits.
          // Recover only edits that have not received trip.updated; they go with the next turn.
          if (event.type === "turn.failed" || event.type === "turn.completed") edits.recover();
          apply(event.session);
          if (event.type === "flights.ready" && viewedTurn !== requestId) {
            viewedTurn = requestId;
            track("planner_results_viewed", { turn_id: requestId, $ai_trace_id: requestId,
              offer_count: event.session.offers.length, category_count: new Set(event.session.recommendations.map((r) => r.category)).size });
          }
          if (event.type === "turn.failed") {
            failed = true;
            if (!disposed) setError(event.message ?? "Please try again.");
          }
          if (event.type === "turn.completed") completed = true;
        });
        if (!completed) throw new Error("The connection ended. Your accepted details are saved; try again.");
        return !failed;
      } catch (cause) {
        edits.recover();
        if (!disposed) {
          if (controller.signal.aborted) {
            if (current) apply({ ...current, status: "interrupted" });
          } else {
            trackError("turn_request_failed", "turn", requestId);
            setError(cause instanceof Error ? cause.message : "Couldn't connect. Please try again.");
            // Refresh the revision after a conflict without automatically repeating paid work.
            await restore().catch(() => {});
          }
        }
        return false;
      } finally {
        running = false;
        activeTurn = undefined;
        controller = null;
        if (!disposed) {
          setBusy(false);
          if (completed && !failed) scheduleEdits();
        }
      }
    }

    const unsubscribe = store.subscribeEdits((patch) => {
      edits.queue(patch);
      setDirty(true);
      scheduleEdits();
    });
    operations.current = {
      send: (text, source) => turn(text, false, source),
      retry: () => { void turn("", true); },
      stop: () => {
        if (activeTurn) track("planner_stop_requested", { turn_id: activeTurn, $ai_trace_id: activeTurn });
        controller?.abort();
      },
      select: async (id) => {
        if (!current || running) return;
        setError(null);
        try {
          const response = await requireResponse(await fetch("/api/planning/selection", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ expectedRevision: current.revision, offerId: id }),
          }));
          apply(await response.json());
        } catch (cause) {
          trackError("selection_request_failed", "selection");
          if (!disposed) setError(cause instanceof Error ? cause.message : "Couldn't save your choice.");
          await restore().catch(() => {});
        }
      },
    };
    void restore().then(scheduleEdits).catch((cause) => {
      if (!boot.signal.aborted) trackError("session_request_failed", "restore");
      if (!disposed) setError(cause instanceof Error ? cause.message : "Couldn't recover your plan.");
    });
    const stopOnLeave = () => {
      if (activeTurn) track("planner_left_during_turn", { turn_id: activeTurn, $ai_trace_id: activeTurn }, true);
      controller?.abort();
    };
    window.addEventListener("pagehide", stopOnLeave);
    return () => {
      disposed = true;
      clearTimeout(timer);
      boot.abort();
      stopOnLeave();
      unsubscribe();
      window.removeEventListener("pagehide", stopOnLeave);
      operations.current = null;
    };
  }, [store]);

  return { session, busy, error, dirty,
    send: (text: string, source?: "chat" | "more_options") => operations.current?.send(text, source) ?? Promise.resolve(false),
    retry: () => operations.current?.retry(),
    stop: () => operations.current?.stop(),
    select: (id: string) => operations.current?.select(id),
  };
}
