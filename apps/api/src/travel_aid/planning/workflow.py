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

from travel_aid.observability import JourneyTrace, current_trace
from travel_aid.planning.chat import PROMPT_VERSION, interpret
from travel_aid.planning.curation import curate
from travel_aid.planning.models import (
    Cabin,
    Category,
    ChatMessage,
    Interpretation,
    Offer,
    PlanningEvent,
    Preferences,
    Recommendation,
    Session,
    Trip,
    TurnRequest,
)
from travel_aid.planning.validation import (
    accept_airports,
    normalize,
    search_details,
    validate_trip,
)
from travel_aid.providers.fli import search_cabin
from travel_aid.recommendations.flights import (
    POLICY_VERSION,
    budget_picks,
    default_reason,
    luxury_picks,
    mid_range_picks,
    mid_range_pool,
    recommendation,
    refresh_budget,
    should_search,
    suitable,
    trace_picks,
    upgrade_note,
)
from travel_aid.settings import get_settings

logger = logging.getLogger(__name__)
EMPTY_CATEGORY: dict[Category, str] = {
    "budget": "No flights met the Budget rules (layovers up to 10 hours).",
    "mid-range": "No other flights met the Mid-range rules (economy with a carry-on likely "
    "included, first flights from 7 AM, and within 1.6× of the cheapest such flight).",
    "luxury": "No other flights met the Luxury rules (layovers up to 4 hours).",
}
Emit = Callable[[PlanningEvent], Awaitable[None]]
Persist = Callable[[Session], Awaitable[None]]


class GraphState(TypedDict):
    session: Session
    interpretation: Interpretation
    question: str | None
    codes: dict[str, list[str]]


async def run_turn(
    session: Session, command: TurnRequest, stop: threading.Event, emit: Emit, persist: Persist
) -> None:
    settings = get_settings()
    trace = current_trace() or JourneyTrace(session.analyticsId, command.requestId)
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
                airports=[],
                preferences=[],
                clarification=None,
                unsupportedTravelers=False,
                searchRequested=False,
                moreOptions=False,
            )
        trace.event(
            "planning_fields_proposed",
            changed_fields=[c.field for c in result.changes],
            preference_fields=[p.field for p in result.preferences],
            prompt_version=PROMPT_VERSION,
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
            trace.event("planning_validation_rejected", reason="invalid_field_value")
            return {
                "question": "Please check those details: use 1–9 adults, a positive USD budget, "
                "and valid flight preferences (stops, departure hour, or cabin).",
                "codes": {},
            }
        errors = validate_trip(trip, local_time.date())
        if errors:
            trace.event("planning_validation_rejected", reason="invalid_trip_dates_or_route")
            return {"question": " ".join(errors), "codes": {}}
        session.trip = trip
        session.preferences = preferences
        for proposal in result.airports:
            place = getattr(trip, proposal.field)
            accepted = accept_airports(place, proposal.codes) if place else []
            if accepted:
                session.placeAirports[normalize(place)] = accepted
        session.placeAirports = dict(list(session.placeAirports.items())[-20:])
        codes, missing = search_details(trip, local_time.date(), session.placeAirports)
        if missing:
            trace.event(
                "planning_resolution_incomplete",
                reason="missing_or_ambiguous_details",
                missing_count=sum(
                    value is None
                    for value in [
                        trip.origin,
                        trip.destination,
                        trip.departureDate,
                        trip.returnDate,
                        trip.travelers,
                    ]
                ),
            )
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
            session.searchDepth = 5
        if result.moreOptions and session.searchDepth >= 10:
            result.clarification = (
                "I've shown the current set of alternatives. "
                "Try different dates or preferences to explore other flights."
            )
        session.recommendations = refresh_budget(
            session.recommendations, session.offers, trip.flightBudgetUsd
        )
        trace.event(
            "planning_details_ready"
            if not missing and not result.clarification
            else "planning_clarification_requested",
            has_flight_budget=trip.flightBudgetUsd is not None,
        )
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
            # Only expand a search that already ran for this route; a new search key clears it.
            more = state["interpretation"].moreOptions and session.searchUpdatedAt is not None
            trace.event(
                "planning_cache_checked",
                cache_hit=cached,
                reason="more_options"
                if more
                else "explicit_refresh"
                if command.retry or state["interpretation"].searchRequested
                else "cache_reuse"
                if cached
                else "cache_miss",
            )
            if more:
                session.searchDepth = min(10, session.searchDepth + 2)
                session.searchedCabins = []
            # Expanding the search is independent of whether old prices can be reused.
            if not cached or (
                not more and (command.retry or state["interpretation"].searchRequested)
            ):
                session.offers = []
                session.recommendations = []
                session.selectedOfferId = None
                session.searchedCabins = []
            # Picks the clearing above left standing stay; new flights land beneath them.
            keep = bool(session.recommendations)
            codes = state["codes"]
            if not keep and any(
                (getattr(session.trip, field) or "").strip().upper() != " ".join(codes[field])
                for field in ("origin", "destination")
            ):
                session.messages.append(
                    ChatMessage(
                        id=str(uuid4()),
                        role="assistant",
                        text=f"Searching {', '.join(codes['origin'])} → "
                        f"{', '.join(codes['destination'])}.",
                    )
                )
            session.status = "searching"
            await event("search.started")
            trace.event(
                "flight_search_started",
                search_depth=session.searchDepth,
                has_flight_budget=session.trip.flightBudgetUsd is not None,
            )
            deadline = time.monotonic() + settings.flight_search_timeout_seconds

            async def search(cabins: list[Cabin]) -> bool:
                """Search cabins in order; False when the provider failed."""
                for cabin in cabins:
                    if cabin in session.searchedCabins:
                        trace.event("flight_cabin_skipped", cabin=cabin, reason="cached_cabin")
                        continue
                    if not should_search(cabin, session.preferences):
                        trace.event(
                            "flight_cabin_skipped",
                            cabin=cabin,
                            policy_version=POLICY_VERSION,
                            reason="explicit_cabin_preference",
                        )
                        continue
                    if stop.is_set():
                        raise asyncio.CancelledError
                    try:
                        with trace.span("flight_cabin_search", cabin=cabin):
                            offers = await asyncio.to_thread(
                                search_cabin,
                                session.trip,
                                codes,
                                session.preferences,
                                cabin,
                                stop,
                                deadline,
                                session.searchDepth,
                            )
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        logger.warning("Flight provider failed for cabin %s", cabin)
                        trace.error("flight_provider_failed", error)
                        trace.event("flight_search_failed", cabin=cabin)
                        return False
                    session.searchedCabins.append(cabin)
                    session.offers = list(
                        {
                            o.id: o
                            for o in session.offers + offers
                            if suitable(o, session.preferences)
                        }.values()
                    )
                    session.searchUpdatedAt = datetime.now(UTC).isoformat()
                return True

            async def reasons(
                category: Category, offers: list[Offer], *, choose: bool = False
            ) -> dict[str, str] | None:
                """Model reasons by offer id, in the model's order; None when unavailable."""
                if not offers:
                    return {}
                context = {
                    "category": category,
                    "flightBudgetUsd": session.trip.flightBudgetUsd,
                    "budgetPickPricesUsd": [
                        o.totalUsd
                        for o in session.offers
                        for r in session.recommendations
                        if r.category == "budget" and r.offerId == o.id
                    ],
                }
                try:
                    with trace.span("flight_curation", category=category):
                        picks = await curate(category, offers, choose=choose, context=context)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    logger.warning("Flight curation failed for %s", category)
                    trace.error("flight_curation_failed", error)
                    return None
                return {pick.offerId: pick.reason.strip()[:300] for pick in picks} or None

            def add(
                category: Category,
                picks: list[Offer],
                written: dict[str, str] | None,
                **notes: object,
            ) -> list[Recommendation]:
                return [
                    recommendation(
                        category,
                        offer,
                        (written or {}).get(offer.id) or default_reason(category, offer),
                        session.trip.flightBudgetUsd,
                        carry_on=category == "mid-range",
                        note=upgrade_note(session.offers, offer) if notes.get("economy") else None,
                    )
                    for offer in picks
                ]

            # Budget and Mid-range need only the first cabin; the others search meanwhile.
            primary: Cabin = session.preferences.cabin or "economy"
            failed = not await search([primary])
            others: list[Cabin] = [c for c in ("premium_economy", "business") if c != primary]
            remaining = asyncio.create_task(search(others)) if not failed else None
            try:
                if keep:
                    if remaining:
                        failed = not await remaining
                    session.recommendations = refresh_budget(
                        session.recommendations, session.offers, session.trip.flightBudgetUsd
                    )
                    await event("flights.ready")
                else:
                    session.recommendations = []
                    used: set[str] = set()
                    picks = budget_picks(session.offers, session.preferences, used)
                    session.recommendations += add("budget", picks, await reasons("budget", picks))
                    used |= {o.id for o in picks}
                    trace_picks("budget", picks, session.offers, "rules")
                    await event("flights.ready")
                    pool = mid_range_pool(session.offers, session.preferences, used)
                    chosen = await reasons("mid-range", pool, choose=True)
                    picks = mid_range_picks(pool, list(chosen) if chosen else None)
                    session.recommendations += add("mid-range", picks, chosen)
                    used |= {o.id for o in picks}
                    by_model = chosen is not None and any(o.id in chosen for o in picks)
                    trace_picks(
                        "mid-range", picks, session.offers, "model" if by_model else "rules"
                    )
                    await event("flights.ready")
                    if remaining:
                        failed = not await remaining
                    picks, economy = luxury_picks(session.offers, session.preferences, used)
                    session.recommendations += add(
                        "luxury", picks, await reasons("luxury", picks), economy=economy
                    )
                    trace_picks("luxury", picks, session.offers, "rules")
                    await event("flights.ready")
            finally:
                if remaining and not remaining.done():
                    remaining.cancel()
            trace.event(
                "flight_search_completed",
                outcome="partial"
                if failed and session.offers
                else "failed"
                if failed
                else "success"
                if session.offers
                else "empty",
                offer_count=len(session.offers),
                category_count=len({r.category for r in session.recommendations}),
            )
            if session.recommendations:
                question = (
                    "Here are round-trip options for all adults. Compare the categories below, "
                    "or tell me your preferences to refine them. Prices can change before booking."
                )
                shown = {r.category for r in session.recommendations}
                missing_categories = [
                    EMPTY_CATEGORY[c] for c in ("budget", "mid-range", "luxury") if c not in shown
                ]
                if missing_categories and not failed:
                    question += " " + " ".join(missing_categories)
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
                    airports=[],
                    preferences=[],
                    clarification=None,
                    unsupportedTravelers=False,
                    searchRequested=False,
                    moreOptions=False,
                ),
            },
            config={"callbacks": trace.callbacks(prompt_version=PROMPT_VERSION)},
        )
    except NodeCancelledError as error:
        if stop.is_set():
            raise asyncio.CancelledError from error
        raise
