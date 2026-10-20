"use client";

import { createContext, use, useState, useSyncExternalStore } from "react";
import { EMPTY_TRIP } from "./trip";
import { createTripStore, type TripStore } from "./trip-store";
import { useTripWebMcpTools } from "./use-trip-webmcp-tools";

const TripStoreContext = createContext<TripStore | null>(null);

export function TripProvider({ children }: { children: React.ReactNode }) {
  const [store] = useState(() => createTripStore());
  useTripWebMcpTools(store);
  return <TripStoreContext value={store}>{children}</TripStoreContext>;
}

function useTripStore(): TripStore {
  const store = use(TripStoreContext);
  if (!store) throw new Error("useTrip must be used inside <TripProvider>.");
  return store;
}

export function useTrip() {
  const store = useTripStore();
  const trip = useSyncExternalStore(store.subscribe, store.getSnapshot, () => EMPTY_TRIP);
  return { trip, updateTrip: store.update };
}
