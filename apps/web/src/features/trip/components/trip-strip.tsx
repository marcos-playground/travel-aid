"use client";

import { useState } from "react";
import { PlusIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { formatDateRange, formatUsd, missingFields, nights, type Trip } from "../trip";
import { useTrip } from "../trip-provider";
import { BudgetEditor, DatesEditor, PlaceEditor, TravelersEditor, type EditorProps } from "./trip-editors";

type Segment = {
  key: string;
  label: string;
  value: (trip: Trip) => React.ReactNode;
  missing: (trip: Trip) => boolean;
  Editor: (props: EditorProps) => React.ReactNode;
};

const SEGMENTS: Segment[] = [
  {
    key: "origin",
    label: "From",
    value: (trip) => trip.origin,
    missing: (trip) => trip.origin === null,
    Editor: (props) => <PlaceEditor {...props} field="origin" />,
  },
  {
    key: "destination",
    label: "To",
    value: (trip) => trip.destination,
    missing: (trip) => trip.destination === null,
    Editor: (props) => <PlaceEditor {...props} field="destination" />,
  },
  {
    key: "dates",
    label: "Dates",
    value: (trip) => {
      const count = nights(trip);
      return (
        <>
          {formatDateRange(trip)}
          {count !== null && (
            <span className="font-normal text-muted-foreground">
              {" "}
              · {count} {count === 1 ? "night" : "nights"}
            </span>
          )}
        </>
      );
    },
    missing: (trip) => trip.departureDate === null || trip.returnDate === null,
    Editor: DatesEditor,
  },
  {
    key: "travelers",
    label: "Travelers",
    value: (trip) => (trip.travelers === 1 ? "1 traveler" : `${trip.travelers} travelers`),
    missing: (trip) => trip.travelers === null,
    Editor: TravelersEditor,
  },
  {
    key: "budget",
    label: "Budget",
    value: (trip) => trip.budgetUsd !== null && formatUsd(trip.budgetUsd),
    missing: (trip) => trip.budgetUsd === null,
    Editor: BudgetEditor,
  },
];

/**
 * The trip summary pinned above the conversation. The assistant fills it in as you chat,
 * and each part opens an editor so you can set or correct it yourself.
 */
export function TripStrip() {
  const { trip, updateTrip } = useTrip();
  const missing = SEGMENTS.filter((segment) => segment.missing(trip));
  const ready = missingFields(trip).length === 0;

  return (
    <section aria-labelledby="trip-strip-title" className="border-b bg-muted">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 pt-3 sm:px-6">
        <h2 id="trip-strip-title" className="font-mono text-xs tracking-widest text-muted-foreground uppercase">
          Your trip · Round trip · 1 room
        </h2>
        {ready ? (
          <Badge>Ready to search</Badge>
        ) : (
          <Badge variant="outline" className="border-transparent bg-warning text-warning-foreground">
            Missing: {missing.map((segment) => segment.label.toLowerCase()).join(", ")}
          </Badge>
        )}
      </div>
      {/* One scrolling row on phones keeps the pinned strip short; five columns from md up. */}
      <div className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-2 pb-2 [scrollbar-width:none] sm:px-4 md:grid md:grid-cols-[1fr_1fr_1.4fr_0.9fr_1fr] md:gap-0 md:overflow-visible">
        {SEGMENTS.map((segment) => (
          <TripSegment key={segment.key} segment={segment} trip={trip} updateTrip={updateTrip} />
        ))}
      </div>
    </section>
  );
}

function TripSegment({
  segment,
  trip,
  updateTrip,
}: { segment: Segment } & Pick<EditorProps, "trip" | "updateTrip">) {
  const [open, setOpen] = useState(false);
  const isMissing = segment.missing(trip);
  const { Editor } = segment;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="group flex max-w-[16rem] shrink-0 flex-col items-start gap-0.5 rounded-lg px-2 py-2 text-left transition-colors outline-none hover:bg-background focus-visible:ring-3 focus-visible:ring-ring/50 aria-expanded:bg-background sm:px-3 md:max-w-none md:min-w-0"
        >
          <span className="font-mono text-[11px] tracking-widest text-muted-foreground uppercase">{segment.label}</span>
          {isMissing ? (
            <span className="inline-flex items-center gap-1 text-sm text-muted-foreground group-hover:text-foreground">
              <PlusIcon className="size-3.5" aria-hidden />
              Add
            </span>
          ) : (
            <span className="max-w-full truncate font-bold tabular-nums">{segment.value(trip)}</span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80">
        <Editor trip={trip} updateTrip={updateTrip} onDone={() => setOpen(false)} />
      </PopoverContent>
    </Popover>
  );
}
