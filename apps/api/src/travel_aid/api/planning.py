"""Anonymous planning API; Fetch POST streams explicit SSE events to the browser."""

import asyncio
import contextlib
import logging
import secrets
import threading
import time
from collections.abc import AsyncIterator
from typing import Annotated
from urllib.parse import urlparse
from uuid import uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from travel_aid.infrastructure.sessions import SessionConflict, SessionRepository
from travel_aid.observability import JourneyTrace, capture, flush, trace_context
from travel_aid.planning.models import (
    PlanningEvent,
    SelectionRequest,
    Session,
    TurnRequest,
)
from travel_aid.planning.workflow import run_turn
from travel_aid.settings import get_settings

router = APIRouter(prefix="/planning", tags=["planning"])
COOKIE = "travel_aid_session"
logger = logging.getLogger(__name__)


class PlanningStream(StreamingResponse):
    media_type = "text/event-stream"


def repository() -> SessionRepository:
    settings = get_settings()
    if not settings.database_url:
        raise HTTPException(503, "Planning is not configured yet. Please try again later.")
    return SessionRepository(settings.database_url, settings.planning_retention_days)


Repo = Annotated[SessionRepository, Depends(repository)]


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    # Local Next rewrites use the API's Host header. Explicitly allow the configured
    # browser origin rather than trusting a caller-supplied forwarded-host header.
    if (
        origin
        and origin.rstrip("/") != get_settings().web_origin.rstrip("/")
        and urlparse(origin).netloc != request.headers.get("host")
    ):
        raise HTTPException(403, "This request must come from Travel Aid.")


def token_from(request: Request) -> str:
    token = request.cookies.get(COOKIE, "")
    if len(token) < 32 or len(token) > 128:
        raise HTTPException(401, "Start a planning session first.")
    return token


def renew_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="lax",
        path="/api/planning",
        secure=request.url.scheme == "https"
        or get_settings().environment in ("production", "preview"),
        max_age=get_settings().planning_retention_days * 86400,
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/session", response_model=Session)
async def restore(request: Request, response: Response, repo: Repo) -> Session:
    check_origin(request)
    token = request.cookies.get(COOKIE, "")
    try:
        session = await repo.get(token) if 32 <= len(token) <= 128 else None
        created = session is None
        if session is None:
            token = secrets.token_urlsafe(32)
            session = await repo.create(token)
    except psycopg.Error as error:
        JourneyTrace(uuid4(), uuid4()).error("session_storage_failed", error)
        await flush()
        raise HTTPException(
            503, "Planning is temporarily unavailable. Please try again."
        ) from error
    renew_cookie(response, request, token)
    capture(
        "planning_session_created" if created else "planning_session_recovered", session.analyticsId
    )
    await flush()
    return session


@router.post("/selection", response_model=Session)
async def select(
    command: SelectionRequest, request: Request, response: Response, repo: Repo
) -> Session:
    check_origin(request)
    try:
        token = token_from(request)
        session = await repo.select(token, command.expectedRevision, command.offerId)
        renew_cookie(response, request, token)
        offer = next(o for o in session.offers if o.id == command.offerId)
        category = next(
            (r.category for r in session.recommendations if r.offerId == command.offerId), None
        )
        capture(
            "flight_selected",
            session.analyticsId,
            category=category,
            cabin=offer.cabin,
            over_budget=bool(
                session.trip.flightBudgetUsd and offer.totalUsd > session.trip.flightBudgetUsd
            ),
            revision=session.revision,
            turn_id=session.lastRequestId,
            **{"$ai_trace_id": session.lastRequestId},
        )
        await flush()
        return session
    except SessionConflict as error:
        raise HTTPException(
            409, "The plan changed. Reload it before selecting this flight."
        ) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except psycopg.Error as error:
        JourneyTrace(uuid4(), uuid4()).error("selection_storage_failed", error)
        await flush()
        raise HTTPException(503, "Couldn't save that choice. Please try again.") from error


@router.post(
    "/messages",
    response_class=PlanningStream,
    responses={
        200: {"model": PlanningEvent, "description": "SSE frames containing planning events."}
    },
    response_model=None,
)
async def messages(command: TurnRequest, request: Request, repo: Repo) -> StreamingResponse:
    check_origin(request)
    token = token_from(request)
    if not command.text.strip() and not command.patch and not command.retry:
        raise HTTPException(422, "Send a message, a trip edit, or a retry request.")
    try:
        session = await repo.claim(token, command.expectedRevision, str(command.requestId))
    except SessionConflict as error:
        capture("planning_error", uuid4(), error_code="revision_conflict", stage="turn_claim")
        await flush()
        raise HTTPException(
            409, "Your plan changed or is busy. Reload it and try again."
        ) from error
    except psycopg.Error as error:
        JourneyTrace(uuid4(), command.requestId).error("turn_storage_failed", error)
        await flush()
        raise HTTPException(
            503, "Planning is temporarily unavailable. Please try again."
        ) from error
    stop = threading.Event()
    queue: asyncio.Queue[PlanningEvent | None] = asyncio.Queue()
    trace = JourneyTrace(session.analyticsId, command.requestId)

    async def emit(event: PlanningEvent) -> None:
        await queue.put(event)

    async def persist(current: Session) -> None:
        await repo.save(token, current)

    async def execute() -> None:
        started = time.monotonic()
        trace.event(
            "planning_turn_started",
            revision=session.revision,
            input_kind="chat" if command.text.strip() else "retry" if command.retry else "edit",
            edited_fields=list(command.patch),
        )
        try:
            with trace_context(trace):
                await run_turn(session, command, stop, emit, persist)
        except asyncio.CancelledError:
            session.status = "interrupted"
            raise
        except Exception as error:
            logger.exception("Planning turn failed")
            session.status = "error"
            trace.error("planning_turn_failed", error)
            await emit(
                PlanningEvent(
                    type="turn.failed",
                    session=session.model_copy(deep=True),
                    message="I couldn't finish that request. Your accepted details "
                    "are saved; please try again.",
                )
            )
        finally:
            stop.set()
            # Release on disconnect too; already accepted details/finished cabin results survive.
            try:
                await asyncio.shield(asyncio.wait_for(repo.save(token, session, release=True), 5))
            except (Exception, asyncio.CancelledError) as error:
                logger.warning("Session cleanup deferred to lease expiry")
                trace.error("session_cleanup_failed", error)
            trace.event(
                "planning_turn_failed" if session.status == "error" else "planning_turn_completed",
                outcome=session.status,
                duration_ms=round((time.monotonic() - started) * 1000),
                offer_count=len(session.offers),
                category_count=len(session.recommendations),
            )
            await emit(PlanningEvent(type="turn.completed", session=session.model_copy(deep=True)))
            await flush()
            await queue.put(None)

    async def stream() -> AsyncIterator[str]:
        task = asyncio.create_task(execute())
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    break
                yield f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"
        finally:
            stop.set()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    response = PlanningStream(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
        },
    )
    renew_cookie(response, request, token)
    return response
