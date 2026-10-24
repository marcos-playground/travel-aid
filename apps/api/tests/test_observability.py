import asyncio
import json
import time
from typing import Any
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from travel_aid import observability as obs
from travel_aid.planning.models import Session
from travel_aid.settings import Settings


class RecordingClient:
    privacy_mode = True

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def capture(
        self, event: str, *, distinct_id: str, properties: dict[str, Any], **kwargs: Any
    ) -> None:
        filtered = obs.before_send(
            {"event": event, "distinct_id": distinct_id, "properties": properties}
        )
        if filtered:
            self.events.append(filtered)


def test_final_boundary_rejects_content_sdk_enrichment_and_auth_ids() -> None:
    session_id = str(uuid4())
    event: dict[str, Any] = {
        "event": "$ai_generation",
        "distinct_id": "cookie-secret",
        "$set": {"name": "Private"},
        "properties": {
            "planning_session_id": session_id,
            "distinct_id": "cookie-secret",
            "$ai_input": [{"content": "private user message"}],
            "$ai_output_choices": "private",
            "$ai_input_state": "graph contains cookie",
            "$ai_tools": [{"secret": "tool"}],
            "$ai_input_tokens": 99,
            "$ai_output_tokens": 10,
            "$ai_model": "gpt-6-luna",
            "$ai_trace_id": str(uuid4()),
            "$current_url": "https://example.com/?token=private",
            "error_type": "postgresql://private",
            "changed_fields": ["origin", "travelers"],
        },
    }
    clean = obs.before_send(event)
    assert clean and clean["distinct_id"] == session_id
    assert clean["properties"]["distinct_id"] == session_id
    assert clean["properties"]["$ai_input_tokens"] == 99
    assert clean["properties"]["$ai_output_tokens"] == 10
    assert clean["properties"]["changed_fields"] == ["origin", "travelers"]
    assert "private" not in json.dumps(clean) and "cookie" not in json.dumps(clean)
    assert "$ai_tools" not in clean["properties"] and "$set" not in clean
    assert obs.before_send({"event": "$autocapture", "properties": {}}) is None
    assert (
        obs.before_send(
            {"event": "planning_error", "properties": {"planning_session_id": "auth-hash"}}
        )
        is None
    )
    assert obs.before_send({"event": "$ai_generation", "properties": None}) is None


@pytest.mark.parametrize("environment", ["production", "development", "test", "preview"])
def test_debug_is_explicit_nonproduction_only(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    settings = Settings(_env_file=None, environment=environment, posthog_capture_debug_content=True)
    monkeypatch.setattr(obs, "get_settings", lambda: settings)
    properties = {
        "planning_session_id": str(uuid4()),
        "$ai_input": [{"role": "user", "content": "Email jane@example.com; sk-privatekey"}],
        "$ai_output_choices": [{"message": {"content": "Phone +1 (809) 555-1234"}}],
        "$ai_input_state": "private graph state",
    }
    result = obs.before_send({"event": "$ai_generation", "properties": properties})
    assert result
    if environment == "production":
        assert "$ai_input" not in result["properties"]
        assert "$ai_output_choices" not in result["properties"]
    else:
        assert "[REDACTED]" in result["properties"]["$ai_input"][0]["content"]
        assert "jane@" not in json.dumps(result) and "555-1234" not in json.dumps(result)
    assert "$ai_input_state" not in result["properties"]
    span = obs.before_send({"event": "$ai_span", "properties": properties})
    assert span and "$ai_input" not in span["properties"]
    assert "$ai_input_state" not in span["properties"]
    monkeypatch.setenv("VERCEL_ENV", "production")
    assert not obs.debug_content_enabled(settings)
    production = obs.before_send({"event": "$ai_generation", "properties": properties})
    assert production and "$ai_input" not in production["properties"]
    assert not obs.debug_content_enabled(Settings(_env_file=None, environment=environment))


def test_errors_keep_locations_without_messages_source_or_locals() -> None:
    result = obs.before_send(
        {
            "event": "$exception",
            "properties": {
                "planning_session_id": str(uuid4()),
                "error_code": "flight_provider_failed",
                "$exception_list": [
                    {
                        "type": "RuntimeError",
                        "value": "raw chat and credentials",
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "/Users/person/file.py",
                                    "context_line": "password = secret",
                                },
                                {
                                    "filename": "travel_aid/providers/fli.py",
                                    "function": "search_cabin",
                                    "lineno": 123,
                                    "in_app": True,
                                    "vars": {"token": "secret"},
                                    "pre_context": ["secret"],
                                },
                            ]
                        },
                    }
                ],
            },
        }
    )
    assert result
    exception = result["properties"]["$exception_list"][0]
    assert exception["value"] == "flight_provider_failed"
    assert exception["stacktrace"]["frames"] == [
        {
            "filename": "travel_aid/providers/fli.py",
            "function": "search_cabin",
            "lineno": 123,
            "in_app": True,
        }
    ]
    assert "secret" not in json.dumps(result) and "raw chat" not in json.dumps(result)


@pytest.mark.parametrize(
    "environment,debug", [("development", False), ("development", True), ("production", True)]
)
def test_real_langchain_callback_content_respects_environment_and_flag(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    debug: bool,
) -> None:
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    settings = Settings(
        _env_file=None, environment=environment, posthog_capture_debug_content=debug
    )
    monkeypatch.setattr(obs, "get_settings", lambda: settings)
    client = RecordingClient()
    client.privacy_mode = not obs.debug_content_enabled(settings)
    monkeypatch.setattr(obs, "client", lambda: client)
    session_id, turn_id, run_id = uuid4(), uuid4(), uuid4()
    handler = obs.JourneyTrace(session_id, turn_id).callbacks()[0]
    handler.on_chat_model_start(
        {"id": ["langchain", "ChatOpenAI"]},
        [[HumanMessage(content="Test conversation jane@example.com")]],
        run_id=run_id,
        invocation_params={"model": "gpt-6-luna"},
    )
    handler.on_llm_end(
        LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content='{"clarification":"Test generated interpretation"}',
                            usage_metadata={
                                "input_tokens": 100,
                                "output_tokens": 20,
                                "total_tokens": 120,
                            },
                            response_metadata={
                                "model_name": "gpt-6-luna",
                                "model_provider": "openai",
                            },
                        )
                    )
                ]
            ]
        ),
        run_id=run_id,
    )
    generation = next(event for event in client.events if event["event"] == "$ai_generation")
    properties = generation["properties"]
    assert properties["$ai_trace_id"] == str(turn_id)
    assert properties["$ai_session_id"] == str(session_id)
    assert properties["$ai_input_tokens"] == 100 and properties["$ai_output_tokens"] == 20
    if debug and environment != "production":
        assert "Test conversation" in json.dumps(properties["$ai_input"])
        assert "Test generated interpretation" in json.dumps(properties["$ai_output_choices"])
        assert "jane@example.com" not in json.dumps(client.events)
        assert "[REDACTED]" in json.dumps(properties["$ai_input"])
    else:
        assert "$ai_input" not in properties and "$ai_output_choices" not in properties
        assert "Test conversation" not in json.dumps(client.events)


def test_telemetry_failure_cannot_break_events_spans_or_flush(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Broken:
        def capture(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("secret")

        def flush(self, **kwargs: Any) -> None:
            raise RuntimeError("secret")

    monkeypatch.setattr(obs, "client", lambda: Broken())
    trace = obs.JourneyTrace(uuid4(), uuid4())
    trace.event("planning_turn_started")
    trace.error("planning_turn_failed", ValueError("secret"))
    with trace.span("flight_cabin_search"):
        pass
    asyncio.run(obs.flush())


def test_flush_has_bounded_application_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    class Slow:
        def flush(self, **kwargs: Any) -> None:
            time.sleep(1.2)

    monkeypatch.setattr(obs, "client", lambda: Slow())

    async def scenario() -> None:
        started = time.monotonic()
        await obs.flush()
        assert time.monotonic() - started < 1.15

    asyncio.run(scenario())


def test_planning_identity_is_independent_and_persisted_in_session_json() -> None:
    session = Session()
    assert isinstance(session.analyticsId, UUID)
    assert Session.model_validate_json(session.model_dump_json()).analyticsId == session.analyticsId
    assert Session().analyticsId != session.analyticsId


def test_debug_redacts_quoted_credentials_and_bearer_tokens() -> None:
    result = obs.redact_debug(
        '{"password":"PRIVATE_VALUE", "token": "PRIVATE_TOKEN"} '
        "Authorization: Bearer PRIVATE_BEARER; password is PRIVATE_PASSWORD"
    )
    assert "PRIVATE_" not in result


def test_generation_redaction_preserves_structure_dates_and_bounds_content() -> None:
    result = obs.redact_content(
        [
            {
                "role": "user",
                "content": "Travel on 2027-02-10; jane@example.com",
                "password": "PRIVATE_PASSWORD",
            }
        ]
    )
    assert result[0]["role"] == "user"
    assert "2027-02-10" in result[0]["content"]
    assert "jane@" not in json.dumps(result) and "PRIVATE_PASSWORD" not in json.dumps(result)
    large = obs.redact_content([{"content": "x" * 100000}, {"content": "more"}])
    assert len(large[0]["content"]) <= 64000
    assert "[TRUNCATED]" in json.dumps(large)


def test_generation_content_excludes_encrypted_reasoning_blocks() -> None:
    result = obs.redact_content(
        [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "reasoning",
                        "encrypted_content": "OPAQUE_PRIVATE_BLOB",
                        "summary": [],
                    },
                    {"type": "text", "text": '{"changes":[]}'},
                ],
                "encrypted_content": "OPAQUE_PRIVATE_BLOB",
            }
        ]
    )
    assert result == [
        {"role": "assistant", "content": [{"type": "text", "text": '{"changes":[]}'}]}
    ]
