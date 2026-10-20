"use client";

import { useId, useState } from "react";
import { format, parseISO } from "date-fns";
import { BedDoubleIcon, PlaneIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { formatAmount, formatDuration, formatLegTimes, formatRating, formatRoute, formatStops } from "../format";
import {
  CATEGORIES,
  combinationTotal,
  flightOffers,
  hotelOffers,
  swapsWithinBudget,
  type Category,
  type Combination,
  type FlightOffer,
  type HotelOffer,
  type RecommendationSet,
} from "../recommendations";

const CATEGORY_TAG: Record<Category, string> = {
  budget: "bg-sunny text-night",
  "mid-range": "bg-lagoon text-night",
  luxury: "bg-hibiscus text-white",
};

/**
 * Results as mix and match: the three category pairs are starting points, and people can
 * pair any flight with any hotel while the total is measured against their budget.
 */
export function RecommendationPicker({ set, budgetUsd }: { set: RecommendationSet; budgetUsd: number | null }) {
  const flights = flightOffers(set);
  const hotels = hotelOffers(set);
  // Start from the Mid-range pair when it's complete, otherwise from the first pair that is.
  const pairs = set.recommendations.filter((recommendation) => recommendation.flight && recommendation.hotel);
  const start = pairs.find((pair) => pair.category === "mid-range") ?? pairs[0];
  const [flightId, setFlightId] = useState(start?.flight?.id ?? flights[0]?.id);
  const [hotelId, setHotelId] = useState(start?.hotel?.id ?? hotels[0]?.id);

  const flight = flights.find((offer) => offer.id === flightId);
  const hotel = hotels.find((offer) => offer.id === hotelId);

  function choose(combination: Combination) {
    setFlightId(combination.flight.id);
    setHotelId(combination.hotel.id);
  }

  return (
    <div className="flex flex-col gap-4">
      <Provenance set={set} />
      {flight && hotel ? (
        <BudgetPanel
          combination={{ flight, hotel }}
          budgetUsd={budgetUsd}
          pairs={pairs.map((pair) => ({ category: pair.category, flight: pair.flight!, hotel: pair.hotel! }))}
          onChoose={choose}
        />
      ) : (
        <p className="rounded-2xl bg-card p-4">
          I couldn&apos;t find a suitable flight and hotel to pair for this trip. Try different dates or a different
          budget.
        </p>
      )}
      {flight && hotel && budgetUsd !== null && combinationTotal({ flight, hotel }) > budgetUsd && (
        <SwapSuggestion
          combination={{ flight, hotel }}
          swaps={swapsWithinBudget({ flight, hotel }, flights, hotels, budgetUsd)}
          budgetUsd={budgetUsd}
          onChoose={choose}
        />
      )}
      <div className="grid gap-5 md:grid-cols-2">
        <OfferList
          title="Choose a flight"
          icon={<PlaneIcon aria-hidden />}
          value={flightId}
          onValueChange={setFlightId}
          items={set.recommendations.map((recommendation) => ({
            category: recommendation.category,
            offer: recommendation.flight,
            render: (offer: FlightOffer) => <FlightDetails flight={offer} />,
            kind: "flight",
          }))}
        />
        <OfferList
          title="Choose a hotel"
          icon={<BedDoubleIcon aria-hidden />}
          value={hotelId}
          onValueChange={setHotelId}
          items={set.recommendations.map((recommendation) => ({
            category: recommendation.category,
            offer: recommendation.hotel,
            render: (offer: HotelOffer) => <HotelDetails hotel={offer} />,
            kind: "hotel",
          }))}
        />
      </div>
      <SaveTripButton />
    </div>
  );
}

function Provenance({ set }: { set: RecommendationSet }) {
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
      {set.isSample && (
        <Badge className="border-transparent bg-warning font-mono tracking-wider text-warning-foreground uppercase">
          Sample data
        </Badge>
      )}
      <span>
        From {set.sources.join(" and ")} · prices checked{" "}
        {/* Shown in the viewer's time zone, which can differ from the server's. */}
        <time dateTime={set.retrievedAt} suppressHydrationWarning>
          {format(parseISO(set.retrievedAt), "MMM d, yyyy, h:mm a")}
        </time>
      </span>
    </p>
  );
}

function CategoryTag({ category }: { category: Category }) {
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 font-mono text-[10.5px] font-bold tracking-widest uppercase",
        CATEGORY_TAG[category],
      )}
    >
      {CATEGORIES[category].label}
    </span>
  );
}

function BudgetDelta({ totalUsd, budgetUsd }: { totalUsd: number; budgetUsd: number }) {
  const left = budgetUsd - totalUsd;
  return (
    <span
      className={cn(
        "rounded-md px-2 py-1 text-sm font-bold whitespace-nowrap tabular-nums",
        left >= 0 ? "bg-positive text-positive-foreground" : "bg-destructive/10 text-destructive",
      )}
    >
      {formatAmount(left)} {left >= 0 ? "left" : "over budget"}
    </span>
  );
}

function BudgetPanel({
  combination,
  budgetUsd,
  pairs,
  onChoose,
}: {
  combination: Combination;
  budgetUsd: number | null;
  pairs: (Combination & { category: Category })[];
  onChoose: (combination: Combination) => void;
}) {
  const { flight, hotel } = combination;
  const total = combinationTotal(combination);
  // Leave a little room past the larger of the total and the budget so neither touches the end.
  const scale = Math.max(total, budgetUsd ?? 0) * 1.04;

  return (
    <section aria-label="Flight and hotel total" className="flex flex-col gap-3 rounded-2xl bg-card p-4 shadow-sm sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div>
          <p className="font-mono text-[11px] font-bold tracking-widest text-muted-foreground uppercase">
            Flight + hotel
          </p>
          <p className="font-heading text-2xl font-extrabold tabular-nums">
            {formatAmount(flight.totalUsd)} + {formatAmount(hotel.totalUsd)} = {formatAmount(total)}
          </p>
        </div>
        {budgetUsd !== null && <BudgetDelta totalUsd={total} budgetUsd={budgetUsd} />}
      </div>

      <div
        role="img"
        aria-label={`Flight ${formatAmount(flight.totalUsd)} plus hotel ${formatAmount(hotel.totalUsd)} equals ${formatAmount(total)}${budgetUsd === null ? "" : ` of a ${formatAmount(budgetUsd)} budget`}`}
        className={cn("relative h-6 rounded-full bg-secondary", budgetUsd !== null && "mt-5")}
      >
        <div
          className="absolute inset-y-0 left-0 flex overflow-hidden rounded-full motion-safe:transition-[width]"
          style={{ width: `${(total / scale) * 100}%` }}
        >
          <span className="grid h-full place-items-center overflow-hidden bg-sea-deep text-[11px] font-bold text-white" style={{ width: `${(flight.totalUsd / total) * 100}%` }}>
            Flight
          </span>
          <span className="grid h-full place-items-center overflow-hidden bg-hibiscus text-[11px] font-bold text-white" style={{ width: `${(hotel.totalUsd / total) * 100}%` }}>
            Hotel
          </span>
        </div>
        {budgetUsd !== null && (
          <div className="absolute -inset-y-1.5 border-l-2 border-dashed border-foreground" style={{ left: `${(budgetUsd / scale) * 100}%` }}>
            <span className="absolute -top-5 -translate-x-1/2 font-mono text-[10px] font-bold whitespace-nowrap">
              {formatAmount(budgetUsd)} budget
            </span>
          </div>
        )}
      </div>

      {pairs.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>Start from:</span>
          {pairs.map((pair) => {
            const active = pair.flight.id === flight.id && pair.hotel.id === hotel.id;
            return (
              <Button
                key={pair.category}
                type="button"
                size="sm"
                variant={active ? "default" : "outline"}
                aria-pressed={active}
                className="rounded-full tabular-nums"
                onClick={() => onChoose(pair)}
              >
                {CATEGORIES[pair.category].label} pair · {formatAmount(combinationTotal(pair))}
              </Button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function SwapSuggestion({
  combination,
  swaps,
  budgetUsd,
  onChoose,
}: {
  combination: Combination;
  swaps: Combination[];
  budgetUsd: number;
  onChoose: (combination: Combination) => void;
}) {
  const total = combinationTotal(combination);
  return (
    <div role="status" className="flex flex-col gap-2 rounded-xl border-l-4 border-hibiscus bg-card px-4 py-3 text-sm">
      <p className="font-bold">This combination is {formatAmount(total - budgetUsd)} over your budget.</p>
      {swaps.length > 0 ? (
        <>
          <p>Closest options that fit:</p>
          <div className="flex flex-wrap gap-2">
            {swaps.map((swap) => {
              const changesFlight = swap.flight.id !== combination.flight.id;
              const changed = changesFlight ? swap.flight : swap.hotel;
              return (
                <Button
                  key={`${swap.flight.id}-${swap.hotel.id}`}
                  type="button"
                  size="sm"
                  variant="outline"
                  className="rounded-full tabular-nums"
                  onClick={() => onChoose(swap)}
                >
                  Use the {CATEGORIES[changed.category].label} {changesFlight ? "flight" : "hotel"} ·{" "}
                  {formatAmount(combinationTotal(swap))}
                </Button>
              );
            })}
          </div>
        </>
      ) : (
        <p>No single swap fits. Try a cheaper pair above, or ask me to look at other dates.</p>
      )}
    </div>
  );
}

type ListItem<T> = {
  category: Category;
  offer: T | null;
  render: (offer: T) => React.ReactNode;
  kind: "flight" | "hotel";
};

function OfferList<T extends FlightOffer | HotelOffer>({
  title,
  icon,
  value,
  onValueChange,
  items,
}: {
  title: string;
  icon: React.ReactNode;
  value: string | undefined;
  onValueChange: (value: string) => void;
  items: ListItem<T>[];
}) {
  const id = useId();
  const titleId = `${id}-title`;
  return (
    <section className="flex min-w-0 flex-col gap-2">
      <h3 id={titleId} className="flex items-center gap-2 font-heading text-lg font-extrabold [&_svg]:size-5">
        {icon}
        {title}
      </h3>
      <RadioGroup value={value} onValueChange={onValueChange} aria-labelledby={titleId} className="gap-2.5">
        {items.map(({ category, offer, render, kind }) =>
          offer ? (
            <label
              key={offer.id}
              htmlFor={`${id}-${offer.id}`}
              className="grid cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] gap-x-3 gap-y-1 rounded-2xl border-2 border-transparent bg-card p-3.5 transition-colors hover:border-border has-[[data-state=checked]]:border-foreground"
            >
              <RadioGroupItem value={offer.id} id={`${id}-${offer.id}`} className="mt-1" />
              {render(offer)}
            </label>
          ) : (
            <p
              key={`${category}-missing`}
              className="flex flex-wrap items-center gap-2 rounded-2xl border-2 border-dashed p-3.5 text-sm text-muted-foreground"
            >
              <CategoryTag category={category} />
              No suitable {CATEGORIES[category].label.toLowerCase()} {kind} is available for this trip.
            </p>
          ),
        )}
      </RadioGroup>
    </section>
  );
}

function OfferPrice({ amount }: { amount: number }) {
  return <span className="text-right font-heading text-lg font-extrabold tabular-nums">{formatAmount(amount)}</span>;
}

function FlightDetails({ flight }: { flight: FlightOffer }) {
  return (
    <>
      <span className="flex flex-wrap items-center gap-1.5 font-bold">
        <CategoryTag category={flight.category} />
        {formatStops(flight.outbound)} · {flight.cabin}
      </span>
      <OfferPrice amount={flight.totalUsd} />
      <span className="col-span-2 col-start-2 text-sm text-muted-foreground">
        {flight.airline} · {formatRoute(flight)} · {formatDuration(flight.outbound.durationMinutes)} out,{" "}
        {formatDuration(flight.inbound.durationMinutes)} back
        <br />
        Out {formatLegTimes(flight.outbound)} · back {formatLegTimes(flight.inbound)} ·{" "}
        {flight.baggage ?? "Baggage not stated"} · {flight.travelers} {flight.travelers === 1 ? "traveler" : "travelers"},
        round trip
      </span>
    </>
  );
}

function HotelDetails({ hotel }: { hotel: HotelOffer }) {
  return (
    <>
      <span className="flex flex-wrap items-center gap-1.5 font-bold">
        <CategoryTag category={hotel.category} />
        {hotel.name}
      </span>
      <OfferPrice amount={hotel.totalUsd} />
      <span className="col-span-2 col-start-2 text-sm text-muted-foreground">
        {[hotel.locationNote ?? hotel.area, hotel.rating ? formatRating(hotel.rating) : "No rating available"].join(" · ")}
        <br />
        {hotel.cancellation ?? "Cancellation terms not stated"} · {hotel.nights} {hotel.nights === 1 ? "night" : "nights"},{" "}
        {hotel.rooms} {hotel.rooms === 1 ? "room" : "rooms"}
        {hotel.taxesIncluded !== true && (
          <>
            {" "}
            <span className="rounded bg-warning px-1.5 py-0.5 text-xs text-warning-foreground">
              {hotel.taxesIncluded === false ? "Taxes and fees not included" : "Taxes and fees not stated"}
            </span>
          </>
        )}
      </span>
    </>
  );
}

/** Saving needs accounts, which aren't built yet. */
function SaveTripButton() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="self-start">
          <Button type="button" disabled className="rounded-full bg-hibiscus px-5 font-heading font-extrabold text-white">
            Save trip
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>Saving trips needs an account, which is coming soon</TooltipContent>
    </Tooltip>
  );
}
