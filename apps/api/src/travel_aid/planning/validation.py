"""Deterministic validation and airport resolution, outside the language model."""

import re
import unicodedata
from datetime import date
from functools import lru_cache
from typing import Any

import airportsdata
from fli.models.airport import Airport

from travel_aid.planning.models import Trip


def validate_trip(trip: Trip, today: date) -> list[str]:
    errors: list[str] = []
    dates: dict[str, date] = {}
    for field, label in [("departureDate", "departure"), ("returnDate", "return")]:
        value = getattr(trip, field)
        if value is None:
            continue
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError
            dates[field] = parsed
            if parsed < today:
                errors.append(f"Choose a {label} date today or later.")
        except ValueError:
            errors.append(f"Use a real {label} date in YYYY-MM-DD format.")
    if len(dates) == 2 and dates["returnDate"] <= dates["departureDate"]:
        errors.append("Choose a return date after departure.")
    if trip.origin and trip.destination and normalize(trip.origin) == normalize(trip.destination):
        errors.append("Choose different departure and destination airports.")
    return errors


def normalize(value: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower(),
    ).strip()


@lru_cache(maxsize=1)
def airport_data() -> dict[str, Any]:
    return airportsdata.load("IATA")


def resolve_airport(value: str) -> tuple[str | None, list[str]]:
    airports = airport_data()
    code = value.strip().upper()
    if code in airports and code in Airport.__members__:
        return code, []
    query = normalize(value)
    exact = [
        code
        for code, airport in airports.items()
        if code in Airport.__members__
        and query in (normalize(airport["city"]), normalize(airport["name"]))
    ]
    if len(exact) == 1:
        return exact[0], []
    candidates = exact or [
        code
        for code, airport in airports.items()
        if code in Airport.__members__
        and len(query) >= 3
        and query in normalize(f"{airport['city']} {airport['name']}")
    ]
    return None, [f"{code} ({airports[code]['name']})" for code in sorted(candidates)[:6]]


def search_details(trip: Trip, today: date) -> tuple[dict[str, str], str | None]:
    needs = validate_trip(trip, today)
    codes: dict[str, str] = {}
    for field, label in [("origin", "departure airport"), ("destination", "destination airport")]:
        value = getattr(trip, field)
        if value is None:
            needs.append(f"your {label}")
            continue
        code, candidates = resolve_airport(value)
        if code:
            codes[field] = code
        elif candidates:
            needs.append(f"which {label}: {', '.join(candidates)}")
        else:
            needs.append(f"a three-letter airport code for {value}")
    for value, label in [
        (trip.departureDate, "departure date (including year)"),
        (trip.returnDate, "return date (including year)"),
        (trip.travelers, "number of adults (1–9)"),
    ]:
        if value is None:
            needs.append(label)
    if len(codes) == 2 and codes["origin"] == codes["destination"]:
        needs.append("different departure and destination airports")
    return codes, ("Please provide " + "; ".join(needs) + ".") if needs else None
