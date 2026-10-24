"use client";

import { useState } from "react";
import { PlusIcon } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { formatDateRange, formatUsd, missingFields, nights, type Trip } from "../trip";
import { useTrip } from "../trip-provider";
import { BudgetEditor, DatesEditor, PlaceEditor, TravelersEditor, type EditorProps } from "./trip-editors";

type Tag = {
  key: string;
  label: string;
  value: (trip: Trip) => React.ReactNode;
  detail: (trip: Trip) => React.ReactNode;
  missing: (trip: Trip) => boolean;
  Editor: (props: EditorProps) => React.ReactNode;
  color: string;
  /** Tilt and width: each tag hangs a little differently. */
  hang: string;
};

const TAGS: Tag[] = [
  {
    key: "origin",
    label: "From",
    value: (trip) => trip.origin,
    detail: () => "Leaving from",
    missing: (trip) => trip.origin === null,
    Editor: (props) => <PlaceEditor {...props} field="origin" />,
    color: "bg-sunny text-night",
    hang: "-rotate-[1.5deg] basis-40",
  },
  {
    key: "destination",
    label: "To",
    value: (trip) => trip.destination,
    detail: () => "Going to",
    missing: (trip) => trip.destination === null,
    Editor: (props) => <PlaceEditor {...props} field="destination" />,
    color: "bg-white text-night",
    hang: "rotate-1 basis-40",
  },
  {
    key: "dates",
    label: "Dates",
    value: (trip) => formatDateRange(trip),
    detail: (trip) => {
      const count = nights(trip);
      return count === null ? null : `${count} ${count === 1 ? "night" : "nights"}`;
    },
    missing: (trip) => trip.departureDate === null || trip.returnDate === null,
    Editor: DatesEditor,
    color: "bg-hibiscus text-white",
    hang: "-rotate-[0.5deg] basis-52",
  },
  {
    key: "travelers",
    label: "Travelers",
    value: (trip) => (trip.travelers === 1 ? "1 traveler" : `${trip.travelers} travelers`),
    detail: () => "1 room",
    missing: (trip) => trip.travelers === null,
    Editor: TravelersEditor,
    color: "bg-white text-night",
    hang: "rotate-[1.5deg] basis-36",
  },
  {
    key: "budget",
    label: "Budget",
    value: (trip) => trip.budgetUsd !== null && formatUsd(trip.budgetUsd),
    detail: () => "Flights + hotel",
    missing: (trip) => trip.budgetUsd === null,
    Editor: BudgetEditor,
    color: "bg-night text-white",
    hang: "-rotate-1 basis-40",
  },
];

function FlightBudgetEditor(props: EditorProps) {
  return <BudgetEditor {...props} field="flightBudgetUsd" />;
}

/**
 * The trip summary pinned above the conversation, as a row of luggage tags. The assistant
 * fills them in as you chat, and each tag opens an editor so you can set or correct it yourself.
 */
export function TripTags({ flightsOnly = false }: { flightsOnly?: boolean }) {
  const { trip, updateTrip } = useTrip();
  const tags = flightsOnly ? TAGS.map((tag): Tag => tag.key === "budget" ? {
    ...tag, label: "Flight budget",
    value: (trip) => trip.flightBudgetUsd !== null && formatUsd(trip.flightBudgetUsd),
    detail: () => "Optional · All adults",
    missing: (trip) => trip.flightBudgetUsd === null,
    Editor: FlightBudgetEditor,
  } : tag.key === "travelers" ? { ...tag, label: "Adults", value: (trip) => `${trip.travelers} adult${trip.travelers === 1 ? "" : "s"}`, detail: () => "Adults only" } : tag) : TAGS;
  const missing = tags.filter((tag) => tag.missing(trip) && (!flightsOnly || tag.key !== "budget"));
  const ready = missingFields(trip).length === 0;

  return (
    <section aria-labelledby="trip-tags-title">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 pt-3 sm:px-6">
        <h2
          id="trip-tags-title"
          className="font-mono text-xs font-bold tracking-widest text-night uppercase dark:text-white"
        >
          Your trip · Round trip{!flightsOnly && " · 1 room"}
        </h2>
        <p
          className={cn(
            "rounded-full px-3 py-0.5 text-sm font-bold",
            ready ? "bg-sunny text-night" : "bg-night/85 text-white",
          )}
        >
          {ready ? (
            flightsOnly ? "✓ Details added" : "✓ Ready to search"
          ) : (
            <>
              {missing.length} {missing.length === 1 ? "detail" : "details"} to go
              {/* The list wraps badly on phones, where the empty tags already show what's missing. */}
              <span className="hidden sm:inline">: {missing.map((tag) => tag.label.toLowerCase()).join(", ")}</span>
            </>
          )}
        </p>
      </div>
      <div className="mx-auto flex max-w-6xl gap-3.5 overflow-x-auto px-4 pt-3 pb-4 [scrollbar-width:none] sm:px-6">
        {tags.map((tag) => (
          <LuggageTag key={tag.key} tag={tag} trip={trip} updateTrip={updateTrip} />
        ))}
      </div>
    </section>
  );
}

function LuggageTag({ tag, trip, updateTrip }: { tag: Tag } & Pick<EditorProps, "trip" | "updateTrip">) {
  const [open, setOpen] = useState(false);
  const isMissing = tag.missing(trip);
  const { Editor } = tag;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      {/* The trigger button carries the tilt, shadow and focus ring; the inner span is clipped to the tag shape. */}
      <PopoverTrigger
        className={cn(
          "group min-w-0 shrink-0 grow rounded-lg text-left drop-shadow-[0_10px_12px_rgb(0_0_0/0.28)] transition-transform outline-none hover:-translate-y-0.5 hover:rotate-0 focus-visible:rotate-0 focus-visible:outline-3 focus-visible:outline-offset-4 focus-visible:outline-white data-popup-open:rotate-0 motion-reduce:transition-none",
          tag.hang,
        )}
      >
        <span
          className={cn(
            "luggage-tag relative grid min-h-22 content-start gap-0.5 py-3 pr-3.5 pl-8",
            tag.color,
          )}
        >
          <span className="font-mono text-[11px] font-bold tracking-[0.14em] uppercase opacity-75">{tag.label}</span>
          {isMissing ? (
            <span className="inline-flex items-center gap-1 font-heading text-lg font-extrabold opacity-85">
              <PlusIcon className="size-4" aria-hidden />
              Add
            </span>
          ) : (
            <>
              <span className="truncate font-heading text-lg leading-tight font-extrabold tabular-nums sm:text-xl">
                {tag.value(trip)}
              </span>
              <span className="text-[13px] opacity-80">{tag.detail(trip)}</span>
            </>
          )}
        </span>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80">
        <Editor trip={trip} updateTrip={updateTrip} onDone={() => setOpen(false)} />
      </PopoverContent>
    </Popover>
  );
}
