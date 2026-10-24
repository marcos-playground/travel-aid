"""Pinned Fli boundary: bounded HTTP work, complete round trips, application-owned offers."""

import hashlib
import json
import math
import threading
import time
from datetime import UTC, datetime
from typing import Any

from fli.models import Airport, FlightSearchFilters, FlightSegment, PassengerInfo, TripType
from fli.models.google_flights.base import FlightResult, MaxStops, SeatType, TimeRestrictions
from fli.search import SearchFlights
from fli.search._concurrency import TokenBucketRateLimiter
from fli.search.client import Client

from travel_aid.planning.models import Cabin, Journey, Leg, Offer, Preferences, Trip

_limiter = TokenBucketRateLimiter(calls=3, period=1.0)


class SearchStopped(Exception):
    pass


class CancellableClient:
    """Override decorated get: Fli's retry decorator would otherwise retry cancellation."""

    def __init__(self, stop: threading.Event, deadline: float):
        self.client = Client()
        self.stop = stop
        self.deadline = deadline

    def check(self) -> None:
        if self.stop.is_set() or time.monotonic() >= self.deadline:
            raise SearchStopped("Flight search stopped.")

    def get(self, url: str, **kwargs: Any) -> Any:
        self.check()
        while not _limiter.acquire(timeout=0.2):
            self.check()
        self.check()
        kwargs["timeout"] = min(10.0, max(0.1, self.deadline - time.monotonic()))
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
    codes: dict[str, str],
    booking_url: str,
    retrieved_at: str,
) -> Offer | None:
    outbound, inbound = pair
    # Upstream contract: outbound.price is the whole round trip for the requested party.
    # Inbound.price may repeat it or differ; summing or multiplying would overcharge.
    price = outbound.price
    if price is None or not math.isfinite(price) or price <= 0 or outbound.currency != "USD":
        return None
    for result, origin, destination, day in [
        (outbound, codes["origin"], codes["destination"], trip.departureDate),
        (inbound, codes["destination"], codes["origin"], trip.returnDate),
    ]:
        if (
            not result.legs
            or result.legs[0].departure_airport.name != origin
            or result.legs[-1].arrival_airport.name != destination
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
    codes: dict[str, str],
    preferences: Preferences,
    cabin: Cabin,
    stop: threading.Event,
    deadline: float,
    top_n: int = 3,
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
    filters = FlightSearchFilters(
        trip_type=TripType.ROUND_TRIP,
        passenger_info=passengers,
        seat_type=seat,
        stops=MaxStops(preferences.maxStops + 1)
        if preferences.maxStops is not None
        else MaxStops.ANY,
        flight_segments=[
            FlightSegment(
                departure_airport=[[Airport[start], 0]],
                arrival_airport=[[Airport[end], 0]],
                travel_date=day,
                time_restrictions=restrictions,
            )
            for start, end, day in [
                (codes["origin"], codes["destination"], trip.departureDate),
                (codes["destination"], codes["origin"], trip.returnDate),
            ]
        ],
    )
    search = SearchFlights()
    search.client = client
    results = search.search(filters, top_n=top_n, currency="USD", language="en-US", country="US")
    now = datetime.now(UTC).isoformat()
    offers: list[Offer] = []
    for pair in results or []:
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
            offers.append(offer)
    return offers
