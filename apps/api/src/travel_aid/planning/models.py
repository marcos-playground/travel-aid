"""Application contracts. Provider objects and model output never go straight to the UI."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
)

Cabin = Literal["economy", "premium_economy", "business"]
Category = Literal["budget", "mid-range", "luxury"]
TripField = Literal[
    "origin",
    "destination",
    "departureDate",
    "returnDate",
    "travelers",
    "budgetUsd",
    "flightBudgetUsd",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class Trip(Contract):
    origin: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    destination: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    departureDate: str | None = None
    returnDate: str | None = None
    travelers: Annotated[int, Field(strict=True, ge=1, le=9)] | None = None
    # This remains the combined flights + hotel budget; never reuse it for flight pricing.
    budgetUsd: (
        Annotated[float, Field(strict=True, gt=0, le=1_000_000, allow_inf_nan=False)] | None
    ) = None
    flightBudgetUsd: (
        Annotated[float, Field(strict=True, gt=0, le=1_000_000, allow_inf_nan=False)] | None
    ) = None

    @field_validator("origin", "destination", mode="before")
    @classmethod
    def trim_place(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class Preferences(Contract):
    maxStops: Annotated[int, Field(strict=True, ge=0, le=2)] | None = None
    earliestDepartureHour: Annotated[int, Field(strict=True, ge=0, le=23)] | None = None
    cabin: Cabin | None = None


class TripChange(Contract):
    field: TripField
    value: StrictStr | StrictInt | StrictFloat | None


class PreferenceChange(Contract):
    field: Literal["maxStops", "earliestDepartureHour", "cabin"]
    value: StrictStr | StrictInt | None


class PlaceAirports(Contract):
    field: Literal["origin", "destination"]
    codes: list[StrictStr]


class Interpretation(Contract):
    """Required nullable fields also satisfy the provider's strict JSON schema contract."""

    changes: list[TripChange]
    # Proposals only: code checks every airport before it is searched.
    airports: list[PlaceAirports]
    preferences: list[PreferenceChange]
    clarification: str | None
    unsupportedTravelers: bool
    searchRequested: bool
    moreOptions: bool


class Leg(Contract):
    origin: str
    destination: str
    airline: str
    airlineCode: str = ""
    flightNumber: str
    departsAt: str
    arrivesAt: str
    durationMinutes: int
    cabin: str


class Journey(Contract):
    legs: list[Leg]
    durationMinutes: int


class Offer(Contract):
    id: str
    outbound: Journey
    inbound: Journey
    cabin: str
    totalUsd: float
    travelers: int
    bookingUrl: str
    retrievedAt: str


class Recommendation(Contract):
    category: Category
    offerId: str
    rationale: str
    overBudgetUsd: float
    overBudgetPercent: float
    carryOn: Literal["likely"] | None = None
    upgradeNote: str | None = None


class ChatMessage(Contract):
    id: str
    role: Literal["user", "assistant"]
    text: str


class Session(Contract):
    # Public correlation only. It is unrelated to the secret session cookie/hash.
    analyticsId: UUID = Field(default_factory=uuid4)
    revision: int = 0
    trip: Trip = Field(default_factory=Trip)
    preferences: Preferences = Field(default_factory=Preferences)
    messages: list[ChatMessage] = Field(default_factory=list)
    offers: list[Offer] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    selectedOfferId: str | None = None
    # Airports accepted for a typed place, keyed by its normalized text.
    placeAirports: dict[str, list[str]] = Field(default_factory=dict)
    status: Literal["idle", "understanding", "searching", "complete", "interrupted", "error"] = (
        "idle"
    )
    searchKey: str | None = None
    searchedCabins: list[Cabin] = Field(default_factory=list)
    searchUpdatedAt: str | None = None
    searchDepth: int = Field(default=5, ge=1, le=10)
    lastRequestId: str | None = None
    updatedAt: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class TurnRequest(Contract):
    requestId: UUID
    expectedRevision: int = Field(ge=0)
    text: str = Field(default="", max_length=4000)
    # Direct UI edits and chat use the same validation/readiness path.
    patch: dict[TripField, StrictStr | StrictInt | StrictFloat | None] = Field(default_factory=dict)
    timezone: str = "UTC"
    retry: bool = False

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Use an IANA time zone.") from error
        return value


class SelectionRequest(Contract):
    expectedRevision: int
    offerId: str


class PlanningEvent(Contract):
    type: Literal[
        "session.updated",
        "trip.updated",
        "search.started",
        "flights.ready",
        "assistant.message",
        "turn.completed",
        "turn.failed",
    ]
    session: Session
    message: str | None = None
