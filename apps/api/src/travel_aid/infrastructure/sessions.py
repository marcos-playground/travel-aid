"""Short PostgreSQL transactions; no connection is held during model/provider calls."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from travel_aid.planning.models import Session
from travel_aid.settings import get_settings


class SessionConflict(Exception):
    pass


class SessionRepository:
    def __init__(self, url: str, retention_days: int = 30):
        self.url = url
        self.retention_days = retention_days

    def expiry(self) -> datetime:
        return datetime.now(UTC) + timedelta(days=self.retention_days)

    @staticmethod
    def key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def connect(self) -> psycopg.AsyncConnection[Any]:
        return await psycopg.AsyncConnection.connect(self.url, autocommit=True, connect_timeout=10)

    async def create(self, token: str) -> Session:
        session = Session()
        async with await self.connect() as connection:
            await connection.execute(
                "INSERT INTO planning_sessions(token_hash, state, expires_at) VALUES (%s,%s,%s)",
                (self.key(token), Jsonb(session.model_dump(mode="json")), self.expiry()),
            )
            # Bounded cleanup on creation; no scheduling service needed for the initial release.
            await connection.execute(
                "DELETE FROM planning_sessions WHERE token_hash IN "
                "(SELECT token_hash FROM planning_sessions WHERE expires_at < now() LIMIT 100)"
            )
        return session

    async def get(self, token: str) -> Session | None:
        async with await self.connect() as connection:
            row = await (
                await connection.execute(
                    "UPDATE planning_sessions SET expires_at=%s, "
                    "state=CASE WHEN run_id IS NOT NULL AND lease_until < now() "
                    "THEN jsonb_set(state, '{status}', '\"interrupted\"') ELSE state END, "
                    "run_id=CASE WHEN lease_until < now() THEN NULL ELSE run_id END, "
                    "lease_until=CASE WHEN lease_until < now() THEN NULL ELSE lease_until END "
                    "WHERE token_hash=%s AND expires_at > now() RETURNING state",
                    (self.expiry(), self.key(token)),
                )
            ).fetchone()
        if not row:
            return None
        return Session.model_validate(row[0])

    async def claim(self, token: str, revision: int, request_id: str) -> Session:
        async with await self.connect() as connection, connection.transaction():
            row = await (
                await connection.execute(
                    "SELECT state FROM planning_sessions WHERE token_hash=%s AND revision=%s "
                    "AND expires_at > now() AND (run_id IS NULL OR lease_until < now()) FOR UPDATE",
                    (self.key(token), revision),
                )
            ).fetchone()
            if row is None:
                raise SessionConflict
            session = Session.model_validate(row[0])
            if session.lastRequestId == request_id:
                raise SessionConflict
            session.revision += 1
            session.lastRequestId = request_id
            session.status = "understanding"
            await connection.execute(
                "UPDATE planning_sessions SET revision=%s, state=%s, run_id=%s, "
                "lease_until=now()+interval '180 seconds', expires_at=%s WHERE token_hash=%s",
                (
                    session.revision,
                    Jsonb(session.model_dump(mode="json")),
                    request_id,
                    self.expiry(),
                    self.key(token),
                ),
            )
        return session

    async def save(self, token: str, session: Session, *, release: bool = False) -> None:
        session.updatedAt = datetime.now(UTC).isoformat()
        async with await self.connect() as connection:
            cursor = await connection.execute(
                "UPDATE planning_sessions SET state=%s, expires_at=%s, "
                "run_id=CASE WHEN %s THEN NULL ELSE run_id END, "
                "lease_until=CASE WHEN %s THEN NULL ELSE lease_until END "
                "WHERE token_hash=%s AND revision=%s AND run_id=%s",
                (
                    Jsonb(session.model_dump(mode="json")),
                    self.expiry(),
                    release,
                    release,
                    self.key(token),
                    session.revision,
                    session.lastRequestId,
                ),
            )
            if cursor.rowcount != 1:
                raise SessionConflict

    async def select(self, token: str, revision: int, offer_id: str) -> Session:
        async with await self.connect() as connection, connection.transaction():
            row = await (
                await connection.execute(
                    "SELECT state FROM planning_sessions WHERE token_hash=%s AND revision=%s "
                    "AND expires_at>now() AND run_id IS NULL FOR UPDATE",
                    (self.key(token), revision),
                )
            ).fetchone()
            if not row:
                raise SessionConflict
            session = Session.model_validate(row[0])
            if not any(offer.id == offer_id for offer in session.offers):
                raise ValueError("This flight is no longer in your current results.")
            session.selectedOfferId = offer_id
            session.revision += 1
            await connection.execute(
                "UPDATE planning_sessions SET state=%s, revision=%s, expires_at=%s "
                "WHERE token_hash=%s",
                (
                    Jsonb(session.model_dump(mode="json")),
                    session.revision,
                    self.expiry(),
                    self.key(token),
                ),
            )
        return session


def main() -> None:
    """Apply the idempotent initial migration using the direct Neon connection."""
    settings = get_settings()
    url = settings.database_url_unpooled or settings.database_url
    if not url:
        raise SystemExit("Set DATABASE_URL_UNPOOLED or DATABASE_URL before running migrate.")

    async def migrate() -> None:
        async with await psycopg.AsyncConnection.connect(url) as connection:
            await connection.execute(Path(__file__).with_name("planning.sql").read_text())

    asyncio.run(migrate())
