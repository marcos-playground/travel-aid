"""A small LangGraph workflow; explicit snapshots persist accepted work between turns."""

import asyncio
import hashlib
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypedDict
from uuid import uuid4
from zoneinfo import ZoneInfo

from langgraph.errors import NodeCancelledError
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from travel_aid.planning.chat import interpret
from travel_aid.planning.models import (
    Cabin,
    ChatMessage,
    Interpretation,
    PlanningEvent,
    Preferences,
    Session,
    Trip,
    TurnRequest,
)
from travel_aid.planning.validation import search_details, validate_trip
from travel_aid.providers.fli import search_cabin
from travel_aid.recommendations.flights import rank, should_search, suitable
from travel_aid.settings import get_settings

logger = logging.getLogger(__name__)
Emit = Callable[[PlanningEvent], Awaitable[None]]
Persist = Callable[[Session], Awaitable[None]]


class GraphState(TypedDict):
    session: Session
    interpretation: Interpretation
    question: str | None
    codes: dict[str, str]


async def run_turn(
    session: Session, command: TurnRequest, stop: threading.Event, emit: Emit, persist: Persist
) -> None:
    settings = get_settings()
    local_time = datetime.now(ZoneInfo(command.timezone))

    async def event(kind: str) -> None:
        await persist(session)
        await emit(PlanningEvent(type=kind, session=session.model_copy(deep=True)))

    async def extract(state: GraphState) -> dict[str, object]:
        if command.text.strip():
            result = await interpret(session, command.text.strip(), local_time)
        else:
            result = Interpretation(
                changes=[],
                preferences=[],
                clarification=None,
                unsupportedTravelers=False,
                searchRequested=False,
                moreOptions=False,
            )
        return {"interpretation": result}

    async def validate(state: GraphState) -> dict[str, object]:
        result = state["interpretation"]
        patch = {change.field: change.value for change in result.changes}
        patch.update(command.patch)  # Explicit form edits take precedence.
        preference_patch = {change.field: change.value for change in result.preferences}
        if result.unsupportedTravelers:
            patch.pop("travelers", None)
            result.clarification = (
                "I can search for adults only right now. How many adults are traveling?"
            )
        try:
            trip = Trip.model_validate(session.trip.model_dump() | patch)
            preferences = Preferences.model_validate(
                session.preferences.model_dump() | preference_patch
            )
        except ValidationError:
            return {
                "question": "Please check those details: use 1–9 adults, a positive USD budget, "
                "and valid flight preferences (stops, departure hour, or cabin).",
                "codes": {},
            }
        errors = validate_trip(trip, local_time.date())
        if errors:
            return {"question": " ".join(errors), "codes": {}}
        session.trip = trip
        session.preferences = preferences
        codes, missing = search_details(trip, local_time.date())
        # Invalidate old route results as soon as accepted constraints change.
        key = hashlib.sha256(
            json.dumps(
                {
                    "codes": codes,
                    "departure": trip.departureDate,
                    "return": trip.returnDate,
                    "adults": trip.travelers,
                    "preferences": preferences.model_dump(),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if key != session.searchKey:
            session.offers = []
            session.recommendations = []
            session.selectedOfferId = None
            session.searchedCabins = []
            session.searchUpdatedAt = None
            session.searchKey = key
            session.searchDepth = 3
        if result.moreOptions and session.searchDepth >= 10:
            result.clarification = (
                "I've shown the current set of alternatives. "
                "Try different dates or preferences to explore other flights."
            )
        session.recommendations = rank(session.offers, trip.flightBudgetUsd, preferences)
        await event("trip.updated")
        return {"codes": codes, "question": result.clarification or missing}

    async def respond(state: GraphState) -> dict[str, object]:
        question = state["question"]
        if not question:
            cached = (
                bool(session.searchUpdatedAt)
                and (
                    datetime.now(UTC) - datetime.fromisoformat(session.searchUpdatedAt or "")
                ).total_seconds()
                < settings.flight_cache_seconds
            )
            more = state["interpretation"].moreOptions and cached
            if more:
                session.searchDepth = min(10, session.searchDepth + 2)
                session.searchedCabins = []
            elif command.retry or state["interpretation"].searchRequested or not cached:
                session.offers = []
                session.recommendations = []
                session.selectedOfferId = None
                session.searchedCabins = []
            session.status = "searching"
            await event("search.started")
            deadline = time.monotonic() + settings.flight_search_timeout_seconds
            failed = False
            for cabin in ("economy", "premium_economy", "business"):
                typed_cabin: Cabin = cabin
                if typed_cabin in session.searchedCabins or not should_search(
                    typed_cabin, session.offers, session.trip.flightBudgetUsd, session.preferences
                ):
                    continue
                if stop.is_set():
                    raise asyncio.CancelledError
                try:
                    offers = await asyncio.to_thread(
                        search_cabin,
                        session.trip,
                        state["codes"],
                        session.preferences,
                        typed_cabin,
                        stop,
                        deadline,
                        session.searchDepth,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("Flight provider failed for cabin %s", cabin)
                    failed = True
                    break
                session.searchedCabins.append(typed_cabin)
                session.offers = list(
                    {
                        o.id: o for o in session.offers + offers if suitable(o, session.preferences)
                    }.values()
                )
                session.searchUpdatedAt = datetime.now(UTC).isoformat()
                session.recommendations = rank(
                    session.offers, session.trip.flightBudgetUsd, session.preferences
                )
                await event("flights.ready")
            session.recommendations = rank(
                session.offers, session.trip.flightBudgetUsd, session.preferences
            )
            if session.recommendations:
                question = (
                    "Here are round-trip options for all adults. Compare the categories below, "
                    "or tell me your preferences to refine them. Prices can change before booking."
                )
                if failed:
                    question += " I couldn't finish every search; you can retry for more options."
            elif failed:
                question = (
                    "I couldn't finish the flight search. Your trip is saved; please try again."
                )
            else:
                question = (
                    "I couldn't find flights matching these details. "
                    "Try different dates or preferences."
                )
            session.status = "error" if failed else "complete"
        else:
            session.status = "idle"
        session.messages.append(ChatMessage(id=str(uuid4()), role="assistant", text=question))
        await event("assistant.message")
        return {}

    if command.text.strip():
        session.messages.append(
            ChatMessage(id=str(command.requestId), role="user", text=command.text.strip())
        )
    # Bound prompt and persisted conversational history; canonical trip/offers live separately.
    session.messages = session.messages[-80:]
    await event("session.updated")
    builder = StateGraph(GraphState)
    builder.add_node("extract", extract)
    builder.add_node("validate", validate)
    builder.add_node("respond", respond)
    builder.add_edge(START, "extract")
    builder.add_edge("extract", "validate")
    builder.add_edge("validate", "respond")
    builder.add_edge("respond", END)
    # DB snapshots are application persistence, not resumable LangGraph checkpoints.
    try:
        await builder.compile().ainvoke(
            {
                "session": session,
                "codes": {},
                "question": None,
                "interpretation": Interpretation(
                    changes=[],
                    preferences=[],
                    clarification=None,
                    unsupportedTravelers=False,
                    searchRequested=False,
                    moreOptions=False,
                ),
            }
        )
    except NodeCancelledError as error:
        if stop.is_set():
            raise asyncio.CancelledError from error
        raise
