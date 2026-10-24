"""Curated PostHog events: no auth identifiers, raw graph state, or unsanitized errors."""

import asyncio
import logging
import math
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from langchain_core.callbacks import BaseCallbackHandler
from posthog import Posthog
from posthog.ai.langchain import CallbackHandler

from travel_aid.settings import Settings, get_settings

logger = logging.getLogger(__name__)
EVENTS = {
    "planning_session_created",
    "planning_session_recovered",
    "planning_turn_started",
    "planning_turn_completed",
    "planning_turn_failed",
    "planning_details_ready",
    "planning_clarification_requested",
    "flight_search_started",
    "flight_search_completed",
    "flight_search_failed",
    "flight_cabin_skipped",
    "flight_results_ranked",
    "flight_selected",
    "planning_error",
    "$ai_trace",
    "$ai_span",
    "$ai_generation",
    "$exception",
    "planning_fields_proposed",
    "planning_validation_rejected",
    "planning_resolution_incomplete",
    "planning_cache_checked",
    "flight_provider_results",
}
META = {
    "environment",
    "service",
    "release",
    "planning_session_id",
    "turn_id",
    "stage",
    "outcome",
    "reason",
    "duration_ms",
    "error_type",
    "error_code",
    "revision",
    "input_kind",
    "edited_fields",
    "changed_fields",
    "preference_fields",
    "missing_count",
    "offer_count",
    "filtered_count",
    "category_count",
    "category",
    "cabin",
    "cache_hit",
    "search_depth",
    "has_flight_budget",
    "over_budget",
    "budget_ratio",
    "policy_version",
    "prompt_version",
    "request_count",
    "http_status",
    "earliest_hour_rule",
    "ranking_score",
    "duration_minutes",
    "stops",
    "relative_price",
    "over_budget_ratio",
    "$ai_trace_id",
    "$ai_session_id",
    "$ai_span_id",
    "$ai_parent_id",
    "$ai_span_name",
    "$ai_latency",
    "$ai_framework",
    "$ai_model",
    "$ai_provider",
    "$ai_http_status",
    "$ai_input_tokens",
    "$ai_output_tokens",
    "$ai_reasoning_tokens",
    "$ai_cache_read_input_tokens",
    "$ai_cache_creation_input_tokens",
    "$ai_cache_creation_5m_input_tokens",
    "$ai_cache_creation_1h_input_tokens",
    "$ai_is_error",
    "$ai_service_tier",
    "$ai_stop_reason",
    "$lib",
    "$lib_version",
    "$process_person_profile",
    "$geoip_disable",
    "distinct_id",
}
GENERATION_CONTENT = {"$ai_input", "$ai_output_choices"}
_current: ContextVar["JourneyTrace | None"] = ContextVar("planning_trace", default=None)


def debug_content_enabled(settings: Settings) -> bool:
    return (
        settings.posthog_capture_debug_content
        and settings.environment in {"development", "test", "preview"}
        and os.getenv("VERCEL_ENV") != "production"
    )


def safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        # Metadata values are codes, versions, enums and IDs, never free text.
        if re.search(r"(?:sk-|ph[cx]_|ghp_|github_pat_|://|@)", value):
            return None
        return value[:100] if re.fullmatch(r"[\w .:/-]{0,100}", value) else None
    if isinstance(value, list):
        return [safe_scalar(item) for item in value[:20] if isinstance(item, (str, int, bool))]
    return None


def before_send(event: dict[str, Any]) -> dict[str, Any] | None:
    """Last boundary after SDK enrichment. Fail closed, including on malformed payloads."""
    try:
        if event.get("event") not in EVENTS:
            return None
        properties = event.get("properties", {})
        session_id = str(UUID(str(properties.get("planning_session_id", ""))))
        clean = {key: safe_scalar(value) for key, value in properties.items() if key in META}
        clean.update(
            {"distinct_id": session_id, "$process_person_profile": False, "$geoip_disable": True}
        )
        if event["event"] == "$exception":
            # Only our application-owned exception representation is accepted.
            clean["$exception_list"] = []
            for exception in properties.get("$exception_list", [])[:5]:
                frames = []
                for frame in exception.get("stacktrace", {}).get("frames", [])[-20:]:
                    filename = frame.get("filename", "")
                    if filename.startswith("travel_aid/") and ".." not in filename:
                        frames.append(
                            {
                                key: safe_scalar(frame.get(key))
                                for key in ("filename", "function", "lineno", "in_app")
                            }
                        )
                clean["$exception_list"].append(
                    {
                        "type": safe_scalar(exception.get("type", "ApplicationError")),
                        "value": clean.get("error_code") or "application_error",
                        "stacktrace": {"frames": frames},
                    }
                )
        if event["event"] == "$ai_generation" and debug_content_enabled(get_settings()):
            for key in GENERATION_CONTENT:
                if key in properties:
                    clean[key] = redact_content(properties[key])
        # Discard arbitrary SDK event attributes as well as its added properties.
        return {
            key: value
            for key, value in event.items()
            if key in {"event", "timestamp", "uuid", "distinct_id"}
        } | {"distinct_id": session_id, "properties": clean}
    except Exception:
        return None


def redact_debug(text: str, *, limit: int = 64000) -> str:
    """Bounded, best-effort diagnostic text; generation capture preserves message structure."""
    truncated = len(text) > limit * 2
    text = text[: limit * 2]
    patterns = [
        r"-----BEGIN [\s\S]*?-----END [^-]*-----",
        r"\b(?:sk-|ph[cx]_|ghp_|github_pat_)[A-Za-z0-9_-]+",
        r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
        r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        r"https?://\S+|(?:postgres(?:ql)?|redis|mysql)://\S+",
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*",
        r"(?i)(?:api[_ -]?key|password|secret|token|authorization|cookie)[\"']?"
        r"\s*(?::|=|\bis\b)\s*[\"']?[^\s\"',;}]+",
        r"(?<!\w)(?!\d{4}-\d{2}-\d{2}(?:\b|T))\+?\d[\d\s().-]{7,}\d(?!\w)",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "[REDACTED]", text)
    if truncated or len(text) > limit:
        marker = "[TRUNCATED]"
        return (text[: max(0, limit - len(marker))] + marker)[:limit]
    return text


def redact_content(value: Any) -> Any:
    """Redact nested native message payloads, capped at 64k text characters per field."""
    remaining = 64000

    def visit(item: Any, depth: int = 0) -> Any:
        nonlocal remaining
        if depth > 12 or remaining <= 0:
            return "[TRUNCATED]"
        if isinstance(item, str):
            clean = redact_debug(item, limit=remaining)
            remaining -= len(clean)
            return clean
        if isinstance(item, dict):
            return {
                str(key): "[REDACTED]"
                if re.fullmatch(
                    r"(?i)(api[_-]?key|password|secret|token|authorization|cookie)", str(key)
                )
                else visit(child, depth + 1)
                for key, child in list(item.items())[:100]
                if key not in {"encrypted_content", "reasoning_content", "thinking", "signature"}
            }
        if isinstance(item, list):
            return [
                visit(child, depth + 1)
                for child in item[:100]
                if not (
                    isinstance(child, dict)
                    and child.get("type") in {"reasoning", "thinking", "redacted_thinking"}
                )
            ]
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, float) and math.isfinite(item):
            return item
        return None

    return visit(value)


@lru_cache(maxsize=1)
def client() -> Posthog | None:
    settings = get_settings()
    if (
        not settings.posthog_enabled
        or not settings.posthog_project_key
        or not settings.posthog_host
    ):
        return None
    try:
        return Posthog(
            settings.posthog_project_key,
            host=settings.posthog_host,
            privacy_mode=not debug_content_enabled(settings),
            before_send=before_send,
            disable_geoip=True,
            enable_exception_autocapture=False,
            capture_exception_code_variables=False,
            debug=False,
            max_queue_size=2000,
            timeout=0.75,
            max_retries=0,
            flush_interval=1,
        )
    except Exception:
        logger.warning("Telemetry initialization failed")
        return None


def capture(event: str, session_id: UUID | str, **properties: Any) -> None:
    try:
        sdk = client()
        if sdk is None:
            return
        settings = get_settings()
        sdk.capture(
            event,
            distinct_id=str(session_id),
            properties={
                "environment": settings.environment,
                "service": "api",
                "planning_session_id": str(session_id),
                "$ai_session_id": str(session_id),
                "$process_person_profile": False,
                **{key: safe_scalar(value) for key, value in properties.items() if key in META},
            },
        )
    except Exception:
        logger.warning("Telemetry event dropped")


async def flush() -> None:
    """Best-effort bounded wait; network timeout also bounds the SDK worker's requests."""
    try:
        sdk = client()
        if sdk is not None:
            await asyncio.wait_for(asyncio.to_thread(sdk.flush, timeout_seconds=0.5), timeout=1)
    except (Exception, asyncio.CancelledError):
        pass


class JourneyTrace:
    def __init__(self, session_id: UUID, turn_id: UUID):
        self.session_id = session_id
        self.turn_id = turn_id

    def event(self, name: str, **properties: Any) -> None:
        capture(
            name,
            self.session_id,
            turn_id=str(self.turn_id),
            **{"$ai_trace_id": str(self.turn_id)},
            **properties,
        )

    def callbacks(self, *, prompt_version: str | None = None) -> list[BaseCallbackHandler]:
        try:
            sdk = client()
            if sdk is None:
                return []
            return [
                CallbackHandler(
                    sdk,
                    distinct_id=str(self.session_id),
                    trace_id=str(self.turn_id),
                    privacy_mode=not debug_content_enabled(get_settings()),
                    properties={
                        "$ai_session_id": str(self.session_id),
                        "planning_session_id": str(self.session_id),
                        "turn_id": str(self.turn_id),
                        "environment": get_settings().environment,
                        "service": "api",
                        "prompt_version": prompt_version,
                    },
                )
            ]
        except Exception:
            return []

    @contextmanager
    def span(self, name: str, **properties: Any) -> Iterator[None]:
        started = time.monotonic()
        outcome = "success"
        try:
            yield
        except BaseException as error:
            outcome = "cancelled" if isinstance(error, asyncio.CancelledError) else "error"
            raise
        finally:
            self.event(
                "$ai_span",
                stage=name,
                outcome=outcome,
                **properties,
                **{
                    "$ai_span_id": str(uuid4()),
                    "$ai_parent_id": str(self.turn_id),
                    "$ai_span_name": name,
                    "$ai_latency": time.monotonic() - started,
                },
            )

    def error(self, code: str, error: BaseException) -> None:
        self.event("planning_error", error_code=code, error_type=type(error).__name__)
        # Preserve useful application stack locations, without messages, source, or locals.
        frames = []
        tb = error.__traceback__
        while tb:
            filename = Path(tb.tb_frame.f_code.co_filename)
            if "travel_aid" in filename.parts:
                relative = "/".join(filename.parts[filename.parts.index("travel_aid") :])
                frames.append(
                    {
                        "filename": relative,
                        "function": tb.tb_frame.f_code.co_name,
                        "lineno": tb.tb_lineno,
                        "in_app": True,
                    }
                )
            tb = tb.tb_next
        try:
            sdk = client()
            if sdk:
                sdk.capture(
                    "$exception",
                    distinct_id=str(self.session_id),
                    properties={
                        "environment": get_settings().environment,
                        "service": "api",
                        "planning_session_id": str(self.session_id),
                        "turn_id": str(self.turn_id),
                        "$ai_trace_id": str(self.turn_id),
                        "error_code": code,
                        "$exception_list": [
                            {
                                "type": type(error).__name__,
                                "value": code,
                                "stacktrace": {"frames": frames},
                            }
                        ],
                    },
                )
        except Exception:
            pass


def current_trace() -> JourneyTrace | None:
    return _current.get()


@contextmanager
def trace_context(trace: JourneyTrace) -> Iterator[None]:
    token = _current.set(trace)
    try:
        yield
    finally:
        _current.reset(token)
