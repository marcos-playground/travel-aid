"""Pinned Fli boundary: bounded HTTP work, complete round trips, application-owned offers."""

import hashlib
import json
import math
import threading
import time
from datetime import UTC, datetime
from typing import Any

from fli.models import Airport, FlightSearchFilters, FlightSegment, PassengerInfo, TripType
from fli.models.google_flights.base import (
    FlightResult,
    MaxStops,
    SeatType,
    SortBy,
    TimeRestrictions,
)
from fli.search import SearchFlights
from fli.search._concurrency import TokenBucketRateLimiter
from fli.search.client import Client

from travel_aid.observability import current_trace
from travel_aid.planning.models import Cabin, Journey, Leg, Offer, Preferences, Trip

_limiter = TokenBucketRateLimiter(calls=3, period=1.0)
# Category policy allows one connection each way unless the user chooses otherwise.
DEFAULT_MAX_STOPS = 1


class SearchStopped(Exception):
    pass


class CancellableClient:
    """Override decorated get: Fli's retry decorator would otherwise retry cancellation."""

    def __init__(self, stop: threading.Event, deadline: float):
        self.client = Client()
        self.stop = stop
        self.deadline = deadline
        self.request_count = 0
        self._count_lock = threading.Lock()

    def check(self) -> None:
        if self.stop.is_set() or time.monotonic() >= self.deadline:
            raise SearchStopped("Flight search stopped.")

    def get(self, url: str, **kwargs: Any) -> Any:
        self.check()
        while not _limiter.acquire(timeout=0.2):
            self.check()
        self.check()
        kwargs["timeout"] = min(10.0, max(0.1, self.deadline - time.monotonic()))
        with self._count_lock:
            self.request_count += 1
        response = self.client._session().get(url, **kwargs)
        self.check()
        response.raise_for_status()
        return response


def journey(result: FlightResult) -> Journey:
    return Journey(
        durationMinutes=result.duration,
        legs=[
            Leg(
                origin=leg.departure_airport.name,
                destination=leg.arrival_airport.name,
                airline=leg.airline.value,
                airlineCode=leg.airline.name.lstrip("_"),
                flightNumber=leg.flight_number,
                departsAt=leg.departure_datetime.isoformat(),
                arrivesAt=leg.arrival_datetime.isoformat(),
                durationMinutes=leg.duration,
                cabin=leg.cabin.name.lower() if leg.cabin else "unknown",
            )
            for leg in result.legs
        ],
    )


def normalize_pair(
    pair: tuple[FlightResult, FlightResult],
    trip: Trip,
    codes: dict[str, list[str]],
    booking_url: str,
    retrieved_at: str,
) -> Offer | None:
    outbound, inbound = pair
    # Upstream contract: outbound.price is the whole round trip for the requested party.
    # Inbound.price may repeat it or differ; summing or multiplying would overcharge.
    price = outbound.price
    if price is None or not math.isfinite(price) or price <= 0 or outbound.currency != "USD":
        return None
    # Separate tickets leave a missed connection unprotected; never offer them.
    if outbound.self_transfer or inbound.self_transfer:
        return None
    for result, origin, destination, day in [
        (outbound, codes["origin"], codes["destination"], trip.departureDate),
        (inbound, codes["destination"], codes["origin"], trip.returnDate),
    ]:
        if (
            not result.legs
            or result.legs[0].departure_airport.name not in origin
            or result.legs[-1].arrival_airport.name not in destination
            or result.legs[0].departure_datetime.date().isoformat() != day
        ):
            return None
    out, ret = journey(outbound), journey(inbound)
    cabins = {leg.cabin for leg in out.legs + ret.legs}
    mixed = outbound.mixed_cabin or inbound.mixed_cabin or len(cabins) > 1
    cabin = "mixed" if mixed else next(iter(cabins))
    identity = json.dumps(
        [out.model_dump(), ret.model_dump(), price, trip.travelers], sort_keys=True
    )
    return Offer(
        id=hashlib.sha256(identity.encode()).hexdigest()[:24],
        outbound=out,
        inbound=ret,
        cabin=cabin,
        totalUsd=price,
        travelers=trip.travelers or 1,
        bookingUrl=booking_url,
        retrievedAt=retrieved_at,
    )


def search_cabin(
    trip: Trip,
    codes: dict[str, list[str]],
    preferences: Preferences,
    cabin: Cabin,
    stop: threading.Event,
    deadline: float,
    top_n: int = 5,
) -> list[Offer]:
    client = CancellableClient(stop, deadline)
    client.check()
    seat = SeatType[cabin.upper()]
    passengers = PassengerInfo(adults=trip.travelers)
    restrictions = (
        TimeRestrictions(earliest_departure=preferences.earliestDepartureHour)
        if preferences.earliestDepartureHour is not None
        else None
    )
    max_stops = DEFAULT_MAX_STOPS if preferences.maxStops is None else preferences.maxStops
    # Economy also feeds Budget, so fetch the cheapest rows as well as Google's best rows.
    sorts = [SortBy.CHEAPEST, SortBy.BEST] if cabin == "economy" else [SortBy.BEST]
    search = SearchFlights()
    search.client = client
    results: list[Any] = []
    for sort in sorts:
        filters = FlightSearchFilters(
            trip_type=TripType.ROUND_TRIP,
            passenger_info=passengers,
            seat_type=seat,
            stops=MaxStops(max_stops + 1),
            sort_by=sort,
            flight_segments=[
                FlightSegment(
                    departure_airport=[[Airport[code], 0] for code in start],
                    arrival_airport=[[Airport[code], 0] for code in end],
                    travel_date=day,
                    time_restrictions=restrictions,
                )
                for start, end, day in [
                    (codes["origin"], codes["destination"], trip.departureDate),
                    (codes["destination"], codes["origin"], trip.returnDate),
                ]
            ],
        )
        found = search.search(filters, top_n=top_n, currency="USD", language="en-US", country="US")
        results.extend(found or [])
    now = datetime.now(UTC).isoformat()
    offers: dict[str, Offer] = {}
    for pair in results:
        client.check()
        if not isinstance(pair, tuple) or len(pair) != 2:
            continue
        link = search.build_flight_booking_url(
            pair,
            currency="USD",
            language="en-US",
            country="US",
            seat_type=seat,
            passenger_info=passengers,
        )
        offer = normalize_pair(pair, trip, codes, link, now)
        if offer:
            offers.setdefault(offer.id, offer)
    trace = current_trace()
    if trace:
        trace.event(
            "flight_provider_results",
            cabin=cabin,
            request_count=client.request_count,
            offer_count=len(offers),
            filtered_count=len(results) - len(offers),
        )
    return list(offers.values())
