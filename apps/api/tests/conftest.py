"""Unit and integration tests never send telemetry to a developer's real project."""

import pytest

from travel_aid import observability
from travel_aid.settings import Settings


@pytest.fixture(autouse=True)
def disable_analytics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(observability, "client", lambda: None)
    monkeypatch.setattr(observability, "get_settings", lambda: Settings(_env_file=None))
