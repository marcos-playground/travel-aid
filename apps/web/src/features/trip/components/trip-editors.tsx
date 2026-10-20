"use client";

import { useState } from "react";
import { startOfToday } from "date-fns";
import type { DateRange } from "react-day-picker";
import { MinusIcon, PlusIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupText } from "@/components/ui/input-group";
import {
  MAX_TRAVELERS,
  TRIP_FIELDS,
  parseTripDate,
  toTripDate,
  type Trip,
  type TripErrors,
  type TripField,
  type TripPatch,
} from "../trip";
import type { TripUpdateResult } from "../trip-store";

export type EditorProps = {
  trip: Trip;
  updateTrip: (patch: TripPatch) => TripUpdateResult;
  onDone: () => void;
};

/** Rejects stale drafts, then applies a patch and closes the editor on success. */
function useSave({ trip, updateTrip, onDone }: EditorProps) {
  const [initialTrip] = useState(trip);
  const [errors, setErrors] = useState<TripErrors>({});
  function save(patch: TripPatch) {
    const conflicts = (Object.keys(patch) as TripField[]).filter((field) => trip[field] !== initialTrip[field]);
    if (conflicts.length > 0) {
      setErrors(Object.fromEntries(conflicts.map((field) => [
        field,
        "This detail changed while you were editing. Close and reopen this editor to use the latest value.",
      ])));
      return;
    }
    const result = updateTrip(patch);
    if (result.ok) {
      setErrors({});
      onDone();
    } else {
      setErrors(result.errors);
    }
  }
  return { errors, save };
}

function EditorActions({ onClear, canClear }: { onClear: () => void; canClear: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <Button type="button" variant="ghost" size="sm" onClick={onClear} disabled={!canClear}>
        Clear
      </Button>
      <Button type="submit" size="sm">
        Save
      </Button>
    </div>
  );
}

export function PlaceEditor(props: EditorProps & { field: "origin" | "destination" }) {
  const { trip, field } = props;
  const { errors, save } = useSave(props);
  const [value, setValue] = useState(trip[field] ?? "");
  const id = `trip-${field}`;
  const error = errors[field];

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        save({ [field]: value.trim() || null });
      }}
    >
      <FieldGroup className="gap-4">
        <Field data-invalid={Boolean(error)}>
          <FieldLabel htmlFor={id}>{field === "origin" ? "Leaving from" : "Going to"}</FieldLabel>
          <Input
            id={id}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={field === "origin" ? "Santo Domingo or SDQ" : "Madrid or MAD"}
            autoComplete="off"
            aria-invalid={Boolean(error)}
            autoFocus
          />
          {error ? <FieldError>{error}</FieldError> : <FieldDescription>City or airport code.</FieldDescription>}
        </Field>
        <EditorActions canClear={trip[field] !== null} onClear={() => save({ [field]: null })} />
      </FieldGroup>
    </form>
  );
}

export function DatesEditor(props: EditorProps) {
  const { trip } = props;
  const { errors, save } = useSave(props);
  const [range, setRange] = useState<DateRange | undefined>(() => ({
    from: trip.departureDate ? (parseTripDate(trip.departureDate) ?? undefined) : undefined,
    to: trip.returnDate ? (parseTripDate(trip.returnDate) ?? undefined) : undefined,
  }));
  const [today] = useState(startOfToday);
  const error = errors.departureDate ?? errors.returnDate;
  const canClear = trip.departureDate !== null || trip.returnDate !== null;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        save({
          departureDate: range?.from ? toTripDate(range.from) : null,
          returnDate: range?.to ? toTripDate(range.to) : null,
        });
      }}
    >
      <FieldGroup className="gap-3">
        <Field data-invalid={Boolean(error)}>
          <FieldLabel>Departure and return</FieldLabel>
          <Calendar
            mode="range"
            selected={range}
            onSelect={setRange}
            defaultMonth={range?.from ?? today}
            disabled={{ before: today }}
            className="mx-auto p-0"
          />
          {error ? (
            <FieldError>{error}</FieldError>
          ) : (
            <FieldDescription>Pick the day you fly out, then the day you fly back. Hotel dates match.</FieldDescription>
          )}
        </Field>
        <EditorActions
          canClear={canClear}
          onClear={() => {
            setRange(undefined);
            save({ departureDate: null, returnDate: null });
          }}
        />
      </FieldGroup>
    </form>
  );
}

export function TravelersEditor(props: EditorProps) {
  const { trip } = props;
  const { errors, save } = useSave(props);
  const [count, setCount] = useState(trip.travelers ?? 1);

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        save({ travelers: count });
      }}
    >
      <FieldGroup className="gap-4">
        <Field data-invalid={Boolean(errors.travelers)}>
          <FieldLabel id="trip-travelers-label">Travelers</FieldLabel>
          <div className="flex items-center gap-3" role="group" aria-labelledby="trip-travelers-label">
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label="Remove a traveler"
              onClick={() => setCount(count - 1)}
              disabled={count <= 1}
            >
              <MinusIcon />
            </Button>
            <output className="w-10 text-center font-mono text-xl tabular-nums" aria-live="polite">
              {count}
            </output>
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label="Add a traveler"
              onClick={() => setCount(count + 1)}
              disabled={count >= MAX_TRAVELERS}
            >
              <PlusIcon />
            </Button>
          </div>
          {errors.travelers ? (
            <FieldError>{errors.travelers}</FieldError>
          ) : (
            <FieldDescription>Everyone shares one hotel room.</FieldDescription>
          )}
        </Field>
        <EditorActions canClear={trip.travelers !== null} onClear={() => save({ travelers: null })} />
      </FieldGroup>
    </form>
  );
}

export function BudgetEditor(props: EditorProps) {
  const { trip } = props;
  const { errors, save } = useSave(props);
  const [value, setValue] = useState(trip.budgetUsd === null ? "" : String(trip.budgetUsd));

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        const amount = Number(value.replace(/[,\s$]/g, ""));
        save({ budgetUsd: value.trim() === "" ? null : amount });
      }}
    >
      <FieldGroup className="gap-4">
        <Field data-invalid={Boolean(errors.budgetUsd)}>
          <FieldLabel htmlFor="trip-budget">Budget for flights and hotel</FieldLabel>
          <InputGroup>
            <InputGroupAddon>
              <InputGroupText>$</InputGroupText>
            </InputGroupAddon>
            <InputGroupInput
              id="trip-budget"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              inputMode="decimal"
              placeholder="2,000"
              autoComplete="off"
              aria-invalid={Boolean(errors.budgetUsd)}
              autoFocus
            />
            <InputGroupAddon align="inline-end">
              <InputGroupText>USD</InputGroupText>
            </InputGroupAddon>
          </InputGroup>
          {errors.budgetUsd ? (
            <FieldError>{errors.budgetUsd}</FieldError>
          ) : (
            <FieldDescription>{TRIP_FIELDS.budgetUsd.description}</FieldDescription>
          )}
        </Field>
        <EditorActions canClear={trip.budgetUsd !== null} onClear={() => save({ budgetUsd: null })} />
      </FieldGroup>
    </form>
  );
}
