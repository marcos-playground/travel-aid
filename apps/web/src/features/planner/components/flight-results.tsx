"use client";

import type { Journey, Offer, Session } from "@travel-aid/api-client";
import { Button } from "@/components/ui/button";
import { formatDuration } from "@/features/recommendations/format";
import { cn } from "@/lib/utils";

const LABELS = { budget: "Budget", "mid-range": "Mid-range", luxury: "Luxury" };
const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const formatUsd = (amount: number) => `${currency.format(amount)} USD`;
function cabinLabel(cabin: string) {
  return cabin === "unknown" ? "Cabin details unavailable" : cabin === "mixed" ? "Mixed cabins" : cabin.replaceAll("_", " ");
}
function localTime(value: string) {
  // Fli's times are airport-local; do not reinterpret them in the browser's time zone.
  return value.slice(0, 16).replace("T", " · ");
}

function Direction({ journey, label }: { journey: Journey; label: string }) {
  const first = journey.legs[0];
  const last = journey.legs.at(-1);
  if (!first || !last) return null;
  return (
    <div className="space-y-1 text-sm">
      <p className="font-bold">{label}: {first.origin} → {last.destination}</p>
      <p>{localTime(first.departsAt)} → {localTime(last.arrivesAt)}</p>
      <p className="text-muted-foreground">{formatDuration(journey.durationMinutes)} · {journey.legs.length === 1 ? "Nonstop" : `${journey.legs.length - 1} stop(s)`}</p>
      <details>
        <summary className="cursor-pointer text-sea-deep dark:text-lagoon">Flight details</summary>
        <ul className="mt-2 space-y-2">
          {journey.legs.map((leg, index) => <li key={index}>
            {leg.airline} {leg.flightNumber} · {leg.origin} → {leg.destination}<br />
            {localTime(leg.departsAt)} → {localTime(leg.arrivesAt)} · {cabinLabel(leg.cabin)}
          </li>)}
        </ul>
      </details>
    </div>
  );
}

function BookingDetails({ offer }: { offer: Offer }) {
  return (
    <div className="space-y-2">
      <a className="block text-sm underline underline-offset-4" href={offer.bookingUrl} target="_blank" rel="noopener noreferrer">Check current price on Google Flights ↗</a>
      <p className="text-xs text-muted-foreground">Checked {new Date(offer.retrievedAt).toLocaleString("en-US")}. Baggage and fare rules are confirmed by the seller.</p>
    </div>
  );
}

export function FlightResults({ session, disabled, onSelect }: {
  session: Session; disabled: boolean; onSelect: (id: string) => void;
}) {
  if (!session.recommendations.length) return null;
  return (
    <section aria-label="Flight recommendations" className="space-y-3">
      <div className="grid items-start gap-4 lg:grid-cols-3">
        {session.recommendations.map((recommendation) => {
          const offer = session.offers.find((offer) => offer.id === recommendation.offerId);
          if (!offer) return null;
          const selected = session.selectedOfferId === offer.id;
          return (
            <article key={recommendation.category} className={cn("space-y-4 rounded-2xl border-2 bg-card p-5", selected ? "border-sea dark:border-lagoon" : "border-border")}>
              <div>
                <h3 className="font-heading text-xl font-extrabold">{LABELS[recommendation.category]}</h3>
                <p className="mt-2 text-2xl font-bold tabular-nums">{formatUsd(offer.totalUsd)}</p>
                <p className="text-sm text-muted-foreground">Round trip · Total for {offer.travelers} adult{offer.travelers === 1 ? "" : "s"}</p>
                <p className="text-sm capitalize">{cabinLabel(offer.cabin)}</p>
                {recommendation.overBudgetUsd > 0 ? (
                  <p className="mt-2 text-sm font-bold">{formatUsd(recommendation.overBudgetUsd)} over flight budget (+{recommendation.overBudgetPercent}%)</p>
                ) : session.trip.flightBudgetUsd ? <p className="mt-2 text-sm">Within your flight budget</p> : null}
              </div>
              <Direction journey={offer.outbound} label="Outbound" />
              <Direction journey={offer.inbound} label="Return" />
              <p className="text-sm text-muted-foreground">{recommendation.rationale}</p>
              <Button className="w-full" variant={selected ? "secondary" : "default"} disabled={disabled} aria-pressed={selected} onClick={() => onSelect(offer.id)}>
                {selected ? "Selected · Saved in this browser" : "Choose this flight"}
              </Button>
              <BookingDetails offer={offer} />
            </article>
          );
        })}
      </div>
      {session.offers.some((offer) => !session.recommendations.some((r) => r.offerId === offer.id)) && (
        <details className="rounded-2xl border bg-card p-4">
          <summary className="cursor-pointer font-bold">Compare more available flights</summary>
          <ul className="mt-4 divide-y">
            {session.offers.filter((offer) => !session.recommendations.some((r) => r.offerId === offer.id)).map((offer) => (
              <li key={offer.id} className="flex flex-wrap items-start justify-between gap-4 py-4 text-sm">
                <div className="space-y-3">
                  <p className="font-bold">{formatUsd(offer.totalUsd)} · {cabinLabel(offer.cabin)}</p>
                  <p className="text-muted-foreground">Round trip · Total for {offer.travelers} adult{offer.travelers === 1 ? "" : "s"}</p>
                  <Direction journey={offer.outbound} label="Outbound" />
                  <Direction journey={offer.inbound} label="Return" />
                  {session.trip.flightBudgetUsd && offer.totalUsd > session.trip.flightBudgetUsd ? <p>{formatUsd(offer.totalUsd - session.trip.flightBudgetUsd)} over flight budget (+{((offer.totalUsd / session.trip.flightBudgetUsd - 1) * 100).toFixed(1)}%)</p> : null}
                  <BookingDetails offer={offer} />
                </div>
                <Button size="sm" variant="outline" disabled={disabled} aria-pressed={session.selectedOfferId === offer.id} onClick={() => onSelect(offer.id)}>{session.selectedOfferId === offer.id ? "Selected · Saved" : "Choose flight"}</Button>
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-xs text-muted-foreground">Quotes from Google Flights. Selecting a flight saves your preference; booking happens with the seller.</p>
    </section>
  );
}
