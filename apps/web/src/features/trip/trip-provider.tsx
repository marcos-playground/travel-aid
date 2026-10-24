"use client";

import { createContext, use, useState, useSyncExternalStore } from "react";
import { EMPTY_TRIP, type Trip } from "./trip";
import { createTripStore, type TripStore } from "./trip-store";
import { useTripWebMcpTools } from "./use-trip-webmcp-tools";

const TripStoreContext = createContext<TripStore | null>(null);

export function TripProvider({ children, initialTrip = EMPTY_TRIP }: { children: React.ReactNode; initialTrip?: Trip }) {
  const [store] = useState(() => createTripStore(initialTrip));
  useTripWebMcpTools(store);
  return <TripStoreContext value={store}>{children}</TripStoreContext>;
}

export function useTripStore(): TripStore {
  const store = use(TripStoreContext);
  if (!store) throw new Error("useTrip must be used inside <TripProvider>.");
  return store;
}

export function useTrip() {
  const store = useTripStore();
  const trip = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  return { trip, updateTrip: store.update };
}
