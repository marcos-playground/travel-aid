"use client";

import { useEffect } from "react";
import { registerWebMcpTools } from "@/lib/webmcp";
import { createTripTools } from "./trip-tools";
import type { TripStore } from "./trip-store";

/** Exposes the trip to in-browser AI agents through WebMCP while the planner is mounted. */
export function useTripWebMcpTools(store: TripStore) {
  useEffect(() => {
    const controller = new AbortController();
    registerWebMcpTools(createTripTools(store), controller.signal);
    return () => controller.abort();
  }, [store]);
}
