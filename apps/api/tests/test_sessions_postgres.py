"""Run against a dedicated test database, never the runtime DATABASE_URL."""

import asyncio
import os
import secrets
from pathlib import Path

import pytest

from travel_aid.infrastructure.sessions import SessionConflict, SessionRepository
from travel_aid.planning.models import Session

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Test PostgreSQL not configured"
)


def test_postgres_claim_persistence_expiry_and_stale_writer() -> None:
    async def scenario() -> None:
        repo = SessionRepository(os.environ["TEST_DATABASE_URL"])
        token = secrets.token_urlsafe(32)
        async with await repo.connect() as connection:
            await connection.execute(
                (
                    Path(__file__).parents[1] / "src/travel_aid/infrastructure/planning.sql"
                ).read_text()
            )
        try:
            initial = await repo.create(token)
            recovered = await repo.get(token)
            assert recovered and recovered.analyticsId == initial.analyticsId
            # Old saved plans receive one stable public ID, without replacing their auth key.
            async with await repo.connect() as connection:
                await connection.execute(
                    "UPDATE planning_sessions SET state=state-'analyticsId' WHERE token_hash=%s",
                    (repo.key(token),),
                )
            legacy = await repo.get(token)
            recovered = await repo.get(token)
            assert legacy and recovered and recovered.analyticsId == legacy.analyticsId
            claims = await asyncio.gather(
                repo.claim(token, 0, "first"), repo.claim(token, 0, "other"), return_exceptions=True
            )
            assert sum(isinstance(result, Session) for result in claims) == 1
            current = next(result for result in claims if isinstance(result, Session))
            current.trip.origin = "SDQ"
            await repo.save(token, current)
            restored = await repo.get(token)
            assert restored and restored.trip.origin == "SDQ" and restored.revision == 1
            assert await repo.get(secrets.token_urlsafe(32)) is None
            async with await repo.connect() as connection:
                await connection.execute(
                    "UPDATE planning_sessions SET lease_until=now()-interval '1 second' "
                    "WHERE token_hash=%s",
                    (repo.key(token),),
                )
            restored = await repo.get(token)
            assert restored and restored.status == "interrupted"
            with pytest.raises(SessionConflict):
                await repo.save(token, current)
            next_turn = await repo.claim(token, 1, "next")
            await repo.save(token, next_turn, release=True)
            with pytest.raises(SessionConflict):
                await repo.claim(token, 2, "next")
            async with await repo.connect() as connection:
                await connection.execute(
                    "UPDATE planning_sessions SET expires_at=now()-interval '1 second' "
                    "WHERE token_hash=%s",
                    (repo.key(token),),
                )
            assert await repo.get(token) is None
        finally:
            async with await repo.connect() as connection:
                await connection.execute(
                    "DELETE FROM planning_sessions WHERE token_hash=%s", (repo.key(token),)
                )

    asyncio.run(scenario())
