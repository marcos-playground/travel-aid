import asyncio
import json
import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fli.models import Airline, Airport
from fli.models.google_flights.base import FlightLeg, FlightResult, SeatType
from pydantic import ValidationError
from starlette.types import Message

from travel_aid import observability as obs
from travel_aid.api.planning import repository
from travel_aid.infrastructure.sessions import SessionConflict
from travel_aid.main import create_app
from travel_aid.planning.models import (
    Interpretation,
    Journey,
    Leg,
    Offer,
    PlanningEvent,
    Preferences,
    Session,
    Trip,
    TripChange,
    TurnRequest,
)
from travel_aid.planning.validation import resolve_airport, search_details
from travel_aid.planning.workflow import run_turn
from travel_aid.providers.fli import CancellableClient, SearchStopped, normalize_pair
from travel_aid.recommendations.flights import rank, should_search


def trip(**changes: Any) -> Trip:
    return Trip.model_validate(
        {
            "origin": "SDQ",
            "destination": "JFK",
            "departureDate": "2099-02-10",
            "returnDate": "2099-02-15",
            "travelers": 2,
            "flightBudgetUsd": 800,
        }
        | changes
    )


def offer(
    id: str, price: float, *, hour: int = 10, cabin: str = "economy", duration: int = 240
) -> Offer:
    def direction(origin: str, destination: str, day: str) -> Journey:
        return Journey(
            durationMinutes=duration,
            legs=[
                Leg(
                    origin=origin,
                    destination=destination,
                    airline="Test airline",
                    flightNumber=id,
                    departsAt=f"{day}T{hour:02}:00:00",
                    arrivesAt=f"{day}T18:00:00",
                    durationMinutes=duration,
                    cabin=cabin,
                )
            ],
        )

    return Offer(
        id=id,
        outbound=direction("SDQ", "JFK", "2099-02-10"),
        inbound=direction("JFK", "SDQ", "2099-02-15"),
        cabin=cabin,
        totalUsd=price,
        travelers=2,
        bookingUrl="https://www.google.com/travel/flights",
        retrievedAt=datetime.now(UTC).isoformat(),
    )


def test_airports_dates_and_optional_separate_budget() -> None:
    codes, question = search_details(
        trip(flightBudgetUsd=None, budgetUsd=2000), datetime.now(UTC).date()
    )
    assert codes == {"origin": "SDQ", "destination": "JFK"} and question is None
    code, choices = resolve_airport("London")
    assert code is None and len(choices) > 1
    assert "return date" in (
        search_details(trip(returnDate="2099-02-09"), datetime.now(UTC).date())[1] or ""
    )
    question = search_details(Trip(), datetime.now(UTC).date())[1] or ""
    assert "departure" in question and "destination" in question and "adults" in question
    assert "budget" not in question.lower()


@pytest.mark.parametrize("value", [True, "2", 2.5, 0, 10])
def test_no_coercion_of_adult_counts(value: Any) -> None:
    with pytest.raises(ValidationError):
        trip(travelers=value)


def test_no_boolean_coercion_at_http_boundary() -> None:
    with pytest.raises(ValidationError):
        TurnRequest(requestId=uuid4(), expectedRevision=0, patch={"travelers": True})


def test_flexible_ranking_and_explicit_over_budget() -> None:
    offers = [
        offer("cheap", 400, hour=4, duration=500),
        offer("nonstop", 820),
        offer("premium-long", 950, cabin="premium_economy", duration=1000),
        offer("business", 1000, cabin="business", duration=250),
    ]
    results = rank(offers, 800, Preferences())
    assert results[0].offerId == "cheap"
    assert results[1].category == "mid-range" and results[1].offerId == "nonstop"
    assert results[1].overBudgetUsd == 20 and results[1].overBudgetPercent == 2.5
    assert results[2].offerId == "business"
    assert not should_search("business", [offer("economy", 400)], 400, Preferences())
    assert should_search("business", [], 400, Preferences(cabin="business"))
    assert all(
        r.offerId != "cheap" for r in rank(offers, 800, Preferences(earliestDepartureHour=5))
    )


def test_normalization_never_sums_return_or_multiplies_by_adults() -> None:
    def result(origin: str, destination: str, day: str, price: float | None) -> FlightResult:
        return FlightResult(
            legs=[
                FlightLeg(
                    airline=Airline.AA,
                    flight_number="123",
                    departure_airport=Airport[origin],
                    arrival_airport=Airport[destination],
                    departure_datetime=datetime.fromisoformat(f"{day}T10:00:00"),
                    arrival_datetime=datetime.fromisoformat(f"{day}T14:00:00"),
                    duration=240,
                    cabin=SeatType.ECONOMY,
                )
            ],
            duration=240,
            stops=0,
            price=price,
            currency="USD",
        )

    outbound = result("SDQ", "JFK", "2099-02-10", 800)
    inbound = result("JFK", "SDQ", "2099-02-15", 900)
    args = (
        trip(),
        {"origin": "SDQ", "destination": "JFK"},
        "https://www.google.com/travel/flights",
        datetime.now(UTC).isoformat(),
    )
    normalized = normalize_pair((outbound, inbound), *args)
    assert normalized and normalized.totalUsd == 800 and normalized.travelers == 2
    outbound.price = None
    assert normalize_pair((outbound, inbound), *args) is None
    outbound.price, outbound.currency = 800, "EUR"
    assert normalize_pair((outbound, inbound), *args) is None


def test_cancelled_transport_makes_no_request() -> None:
    stop = threading.Event()
    stop.set()
    with pytest.raises(SearchStopped):
        CancellableClient(stop, float("inf")).get("https://invalid.example")


def test_disconnect_preserves_completed_cabin_and_stops_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Session(trip=trip(flightBudgetUsd=None))
    stop = threading.Event()
    searched: list[str] = []
    snapshots: list[Session] = []

    def search(*args: Any) -> list[Offer]:
        searched.append(args[3])
        return [offer("completed", 700)]

    async def persist(value: Session) -> None:
        snapshots.append(value.model_copy(deep=True))

    async def emit(value: PlanningEvent) -> None:
        if value.type == "flights.ready":
            stop.set()  # Simulate the disconnect signal after one completed cabin.

    monkeypatch.setattr("travel_aid.planning.workflow.search_cabin", search)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            run_turn(
                session,
                TurnRequest(requestId=uuid4(), expectedRevision=0, retry=True),
                stop,
                emit,
                persist,
            )
        )
    assert searched == ["economy"]
    assert snapshots[-1].offers[0].id == "completed"


def test_workflow_auto_search_event_order_and_budget_rerank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    events: list[PlanningEvent] = []
    saved: list[Session] = []
    session = Session(trip=trip())

    def search(*args: Any) -> list[Offer]:
        calls.append(args[3])
        return [offer("e", 700)]

    async def persist(value: Session) -> None:
        saved.append(value.model_copy(deep=True))

    async def emit(value: PlanningEvent) -> None:
        events.append(value)

    monkeypatch.setattr("travel_aid.planning.workflow.search_cabin", search)
    command = TurnRequest(requestId=uuid4(), expectedRevision=0, patch={"travelers": 2})
    asyncio.run(run_turn(session, command, threading.Event(), emit, persist))
    assert calls == ["economy"]
    types = [event.type for event in events]
    assert (
        types.index("trip.updated") < types.index("search.started") < types.index("flights.ready")
    )
    assert saved[-1].offers[0].id == "e" and saved[-1].status == "complete"
    command = TurnRequest(requestId=uuid4(), expectedRevision=0, patch={"flightBudgetUsd": 810})
    asyncio.run(run_turn(session, command, threading.Event(), emit, persist))
    assert calls == ["economy"]  # Same route, cached results, only budget changed.
    command = TurnRequest(requestId=uuid4(), expectedRevision=0, patch={"destination": None})
    asyncio.run(run_turn(session, command, threading.Event(), emit, persist))
    assert session.offers == [] and "destination" in session.messages[-1].text


def test_workflow_clarifies_without_search_and_preserves_unmentioned_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Session(trip=trip(destination=None))

    async def extract(*args: Any) -> Interpretation:
        return Interpretation(
            changes=[],
            preferences=[],
            clarification=None,
            unsupportedTravelers=False,
            searchRequested=False,
            moreOptions=False,
        )

    async def noop(value: Any) -> None:
        pass

    def forbidden(*args: Any) -> None:
        pytest.fail("Must not search with missing information")

    monkeypatch.setattr("travel_aid.planning.workflow.interpret", extract)
    monkeypatch.setattr("travel_aid.planning.workflow.search_cabin", forbidden)
    command = TurnRequest(requestId=uuid4(), expectedRevision=0, text="Hello")
    asyncio.run(run_turn(session, command, threading.Event(), noop, noop))
    assert session.trip.origin == "SDQ" and session.trip.travelers == 2
    assert "destination" in session.messages[-1].text


@pytest.mark.parametrize("fresh", [True, False])
def test_more_options_expands_depth_even_after_cache_expires(
    monkeypatch: pytest.MonkeyPatch,
    fresh: bool,
) -> None:
    session = Session(trip=trip())
    calls: list[tuple[str, int]] = []

    def search(*args: Any) -> list[Offer]:
        calls.append((args[3], args[6]))
        return [offer(f"depth-{args[6]}", 700)]

    async def noop(value: Any) -> None:
        pass

    async def more(*args: Any) -> Interpretation:
        return Interpretation(
            changes=[],
            preferences=[],
            clarification=None,
            unsupportedTravelers=False,
            searchRequested=True,
            moreOptions=True,
        )

    monkeypatch.setattr("travel_aid.planning.workflow.search_cabin", search)
    asyncio.run(
        run_turn(
            session,
            TurnRequest(requestId=uuid4(), expectedRevision=0, retry=True),
            threading.Event(),
            noop,
            noop,
        )
    )
    session.selectedOfferId = "depth-3"
    if not fresh:
        session.searchUpdatedAt = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    monkeypatch.setattr("travel_aid.planning.workflow.interpret", more)
    asyncio.run(
        run_turn(
            session,
            TurnRequest(requestId=uuid4(), expectedRevision=0, text="More options"),
            threading.Event(),
            noop,
            noop,
        )
    )
    assert calls == [("economy", 3), ("economy", 5)]
    assert session.searchDepth == 5
    if fresh:
        assert {o.id for o in session.offers} == {"depth-3", "depth-5"}
        assert session.selectedOfferId == "depth-3"
    else:
        assert [o.id for o in session.offers] == ["depth-5"]
        assert session.selectedOfferId is None


@pytest.mark.parametrize("route_change", [False, True])
def test_more_options_does_not_expand_a_new_search(
    monkeypatch: pytest.MonkeyPatch,
    route_change: bool,
) -> None:
    session = Session(trip=trip())
    calls: list[tuple[str, int]] = []

    def search(*args: Any) -> list[Offer]:
        calls.append((args[3], args[6]))
        return [offer(f"depth-{args[6]}", 700)]

    async def noop(value: Any) -> None:
        pass

    async def more(*args: Any) -> Interpretation:
        return Interpretation(
            changes=[TripChange(field="departureDate", value="2099-02-11")] if route_change else [],
            preferences=[],
            clarification=None,
            unsupportedTravelers=False,
            searchRequested=True,
            moreOptions=True,
        )

    monkeypatch.setattr("travel_aid.planning.workflow.search_cabin", search)
    monkeypatch.setattr("travel_aid.planning.workflow.interpret", more)
    if route_change:
        asyncio.run(
            run_turn(
                session,
                TurnRequest(requestId=uuid4(), expectedRevision=0, retry=True),
                threading.Event(),
                noop,
                noop,
            )
        )
        calls.clear()
    asyncio.run(
        run_turn(
            session,
            TurnRequest(requestId=uuid4(), expectedRevision=0, text="More options"),
            threading.Event(),
            noop,
            noop,
        )
    )
    assert calls == [("economy", 3)]
    assert session.searchDepth == 3


class MemoryRepository:
    """API test double only; production never falls back to process-local sessions."""

    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.running = False

    async def create(self, token: str) -> Session:
        self.sessions[token] = Session()
        return self.sessions[token].model_copy(deep=True)

    async def get(self, token: str) -> Session | None:
        value = self.sessions.get(token)
        return value.model_copy(deep=True) if value else None

    async def claim(self, token: str, revision: int, request_id: str) -> Session:
        state = self.sessions.get(token)
        if (
            state is None
            or self.running
            or state.revision != revision
            or state.lastRequestId == request_id
        ):
            raise SessionConflict
        state.revision += 1
        state.lastRequestId = request_id
        self.running = True
        return state.model_copy(deep=True)

    async def save(self, token: str, session: Session, *, release: bool = False) -> None:
        self.sessions[token] = session.model_copy(deep=True)
        if release:
            self.running = False


def test_http_cookie_recovery_sse_and_version_conflict() -> None:
    app = create_app()
    repo = MemoryRepository()
    app.dependency_overrides[repository] = lambda: repo
    with TestClient(app) as client:
        response = client.post("/api/planning/session")
        assert response.status_code == 200 and "HttpOnly" in response.headers["set-cookie"]
        assert "no-store" in response.headers["cache-control"]
        initial_analytics_id = response.json()["analyticsId"]
        body = {"requestId": str(uuid4()), "expectedRevision": 0, "patch": {"origin": "SDQ"}}
        response = client.post("/api/planning/messages", json=body)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "event: trip.updated" in response.text and "event: turn.completed" in response.text
        assert client.post("/api/planning/messages", json=body).status_code == 409
        recovered = client.post("/api/planning/session").json()
        assert recovered["analyticsId"] == initial_analytics_id
        assert recovered["trip"]["origin"] == "SDQ" and recovered["revision"] == 1
        assert (
            client.post(
                "/api/planning/session", headers={"origin": "https://elsewhere.test"}
            ).status_code
            == 403
        )
    with TestClient(app) as other:
        assert other.post("/api/planning/messages", json=body).status_code == 401
        assert other.post("/api/planning/session").json()["trip"]["origin"] is None


def test_asgi_disconnect_releases_lease_and_persists_accepted_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        app = create_app()
        repo = MemoryRepository()
        app.dependency_overrides[repository] = lambda: repo
        token = "browser-test-session-token-with-enough-entropy"
        await repo.create(token)

        async def waiting_turn(
            state: Session, command: TurnRequest, stop: threading.Event, emit: Any, persist: Any
        ) -> None:
            state.trip.origin = "SDQ"
            state.status = "searching"
            await persist(state)
            await emit(PlanningEvent(type="search.started", session=state.model_copy(deep=True)))
            await asyncio.Event().wait()

        monkeypatch.setattr("travel_aid.api.planning.run_turn", waiting_turn)
        incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        await incoming.put(
            {
                "type": "http.request",
                "body": json.dumps(
                    {
                        "requestId": str(uuid4()),
                        "expectedRevision": 0,
                        "text": "Search",
                    }
                ).encode(),
                "more_body": False,
            }
        )

        async def send(message: Message) -> None:
            if message["type"] == "http.response.body" and b"search.started" in message.get(
                "body", b""
            ):
                await incoming.put({"type": "http.disconnect"})

        await asyncio.wait_for(
            app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0", "spec_version": "2.3"},
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/api/planning/messages",
                    "raw_path": b"/api/planning/messages",
                    "query_string": b"",
                    "root_path": "",
                    "headers": [
                        (b"host", b"testserver"),
                        (b"content-type", b"application/json"),
                        (b"cookie", f"travel_aid_session={token}".encode()),
                    ],
                    "server": ("testserver", 80),
                    "client": ("127.0.0.1", 1234),
                },
                incoming.get,
                send,
            ),
            timeout=3,
        )
        assert not repo.running
        assert repo.sessions[token].status == "interrupted"
        assert repo.sessions[token].trip.origin == "SDQ"

    asyncio.run(scenario())


def test_observability_explains_cabin_decisions_without_fares_or_trip_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures: list[dict[str, Any]] = []

    class RecordingClient:
        def capture(self, event: str, **kwargs: Any) -> None:
            filtered = obs.before_send({"event": event, **kwargs})
            if filtered:
                captures.append(filtered)

    monkeypatch.setattr(obs, "client", lambda: RecordingClient())
    # Model callbacks have their own usage/privacy test; this turn uses explicit form edits.
    monkeypatch.setattr(obs.JourneyTrace, "callbacks", lambda self, **kwargs: [])
    monkeypatch.setattr(
        "travel_aid.planning.workflow.search_cabin", lambda *args: [offer("e", 700)]
    )
    session = Session(trip=trip())
    command = TurnRequest(requestId=uuid4(), expectedRevision=0, patch={"travelers": 2})

    async def noop(value: Any) -> None:
        pass

    with obs.trace_context(obs.JourneyTrace(session.analyticsId, command.requestId)):
        asyncio.run(run_turn(session, command, threading.Event(), noop, noop))
    skipped = [e["properties"] for e in captures if e["event"] == "flight_cabin_skipped"]
    assert {(e["cabin"], e["reason"]) for e in skipped} == {
        ("premium_economy", "budget_headroom"),
        ("business", "budget_headroom"),
    }
    assert all(e["turn_id"] == str(command.requestId) for e in skipped)
    ranked = [e["properties"] for e in captures if e["event"] == "flight_results_ranked"]
    assert ranked and all(e["ranking_score"] == 1 for e in ranked)
    raw = json.dumps(captures)
    assert "SDQ" not in raw and "JFK" not in raw and "2099" not in raw
    assert "totalUsd" not in raw and "flightBudgetUsd" not in raw
