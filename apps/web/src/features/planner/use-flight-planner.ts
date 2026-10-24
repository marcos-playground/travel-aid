"use client";

import { useEffect, useRef, useState } from "react";
import type { PlanningEvent, Session } from "@travel-aid/api-client";
import type { TripPatch } from "@/features/trip/trip";
import { useTripStore } from "@/features/trip/trip-provider";
import { readPlanningStream } from "./stream";

type Operations = {
  send: (text: string) => Promise<boolean>;
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
    let pending: TripPatch = {};
    let submitted: TripPatch = {};
    let running = false;
    let controller: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const boot = new AbortController();

    function apply(next: Session) {
      if (disposed || (current && next.revision < current.revision)) return;
      current = next;
      setSession(next);
      // Server hydration must not be mistaken for a manual edit. Edits made during
      // an in-flight turn stay visible and are sent next, rather than overwritten.
      store.replace({ ...next.trip, ...submitted, ...pending });
      setDirty(Object.keys(pending).length > 0 || Object.keys(submitted).length > 0);
    }

    async function restore() {
      const response = await requireResponse(await fetch("/api/planning/session", {
        method: "POST", signal: boot.signal, cache: "no-store",
      }));
      const next: Session = await response.json();
      apply(next);
      return next;
    }

    function scheduleEdits() {
      clearTimeout(timer);
      if (!disposed && !running && current && Object.keys(pending).length) {
        timer = setTimeout(() => { void turn(""); }, 350);
      }
    }

    async function turn(text: string, retry = false): Promise<boolean> {
      if (disposed || running) return false;
      running = true;
      setBusy(true);
      setError(null);
      const patch = pending;
      pending = {};
      submitted = patch;
      controller = new AbortController();
      let completed = false;
      let failed = false;
      try {
        const snapshot = current ?? await restore();
        const response = await requireResponse(await fetch("/api/planning/messages", {
          method: "POST", headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({ text, patch, retry, requestId: crypto.randomUUID(),
            expectedRevision: snapshot.revision,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC" }),
        }));
        if (!response.body) throw new Error("The response stream is unavailable. Please try again.");
        await readPlanningStream(response.body, (value) => {
          if (!value || typeof value !== "object" || !("type" in value) || !("session" in value)) return;
          const event = value as PlanningEvent;
          if (event.type === "trip.updated" || event.type === "turn.completed") submitted = {};
          apply(event.session);
          if (event.type === "turn.failed") {
            failed = true;
            if (!disposed) setError(event.message ?? "Please try again.");
          }
          if (event.type === "turn.completed") completed = true;
        });
        if (!completed) throw new Error("The connection ended. Your accepted details are saved; try again.");
        return !failed;
      } catch (cause) {
        pending = { ...patch, ...pending };
        submitted = {};
        if (!disposed) {
          if (controller.signal.aborted) {
            if (current) apply({ ...current, status: "interrupted" });
          } else {
            setError(cause instanceof Error ? cause.message : "Couldn't connect. Please try again.");
            // Refresh the revision after a conflict without automatically repeating paid work.
            await restore().catch(() => {});
          }
        }
        return false;
      } finally {
        running = false;
        controller = null;
        if (!disposed) {
          setBusy(false);
          if (completed && !failed) scheduleEdits();
        }
      }
    }

    const unsubscribe = store.subscribeEdits((patch) => {
      pending = { ...pending, ...patch };
      setDirty(true);
      scheduleEdits();
    });
    operations.current = {
      send: (text) => turn(text),
      retry: () => { void turn("", true); },
      stop: () => controller?.abort(),
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
          if (!disposed) setError(cause instanceof Error ? cause.message : "Couldn't save your choice.");
          await restore().catch(() => {});
        }
      },
    };
    void restore().then(scheduleEdits).catch((cause) => {
      if (!disposed) setError(cause instanceof Error ? cause.message : "Couldn't recover your plan.");
    });
    const stopOnLeave = () => controller?.abort();
    window.addEventListener("pagehide", stopOnLeave);
    return () => {
      disposed = true;
      clearTimeout(timer);
      boot.abort();
      controller?.abort();
      unsubscribe();
      window.removeEventListener("pagehide", stopOnLeave);
      operations.current = null;
    };
  }, [store]);

  return { session, busy, error, dirty,
    send: (text: string) => operations.current?.send(text) ?? Promise.resolve(false),
    retry: () => operations.current?.retry(),
    stop: () => operations.current?.stop(),
    select: (id: string) => operations.current?.select(id),
  };
}
