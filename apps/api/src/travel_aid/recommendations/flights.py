"""Category rules from the Flight Recommendations wiki page.

Code enforces every hard rule here; the model only chooses among Mid-range candidates and
writes reasons. No model-generated price or cabin claims.
"""

from collections.abc import Iterable
from datetime import datetime

from travel_aid.observability import current_trace
from travel_aid.planning.models import Cabin, Category, Journey, Offer, Preferences, Recommendation
from travel_aid.recommendations.carry_on import CARRY_ON_FEE_AIRLINES

POLICY_VERSION = "flight-categories-v2"
PICKS = 3
DEFAULT_MAX_STOPS = 1
CABIN_RANK = {"economy": 1, "premium_economy": 2, "business": 3}
# An upgrade qualifies below these multiples of the economy price for the same flights.
UPGRADE_LIMIT = {"premium_economy": 1.5, "business": 2.5}
MID_RANGE_CEILING = 1.6
EARLIEST_HOUR: dict[Category, int] = {"mid-range": 7, "luxury": 9}
MAX_LAYOVER_MINUTES: dict[Category, int] = {"budget": 600, "luxury": 240}
# Fallback trade-off when the model is unavailable: USD per traveler per hour saved.
HOUR_VALUE_USD = 40
CABIN_NAMES = {
    "economy": "Economy",
    "premium_economy": "Premium economy",
    "business": "Business",
    "mixed": "Mixed cabins",
    "unknown": "Cabin not reported",
}


def should_search(cabin: Cabin, preferences: Preferences) -> bool:
    return preferences.cabin is None or cabin == preferences.cabin


def max_stops(preferences: Preferences) -> int:
    return DEFAULT_MAX_STOPS if preferences.maxStops is None else preferences.maxStops


def directions(offer: Offer) -> tuple[Journey, Journey]:
    return offer.outbound, offer.inbound


def departs(journey: Journey) -> datetime:
    return datetime.fromisoformat(journey.legs[0].departsAt)


def departs_from(offer: Offer, hour: int) -> bool:
    """Only the first flight of each direction counts, in its airport's local time."""
    return all(departs(direction).hour >= hour for direction in directions(offer))


def stops(offer: Offer) -> int:
    return sum(len(direction.legs) - 1 for direction in directions(offer))


def hours(offer: Offer) -> float:
    return sum(direction.durationMinutes for direction in directions(offer)) / 60


def longest_layover(offer: Offer) -> int:
    return max(
        (
            int(
                (
                    datetime.fromisoformat(after.departsAt)
                    - datetime.fromisoformat(before.arrivesAt)
                ).total_seconds()
                // 60
            )
            for direction in directions(offer)
            for before, after in zip(direction.legs, direction.legs[1:], strict=False)
        ),
        default=0,
    )


def airlines(offer: Offer) -> frozenset[str]:
    return frozenset(
        leg.airlineCode or leg.airline for direction in directions(offer) for leg in direction.legs
    )


def flights(offer: Offer) -> tuple[str, ...]:
    return tuple(
        f"{leg.airlineCode or leg.airline} {leg.flightNumber}"
        for direction in directions(offer)
        for leg in direction.legs
    )


def suitable(offer: Offer, preferences: Preferences) -> bool:
    for direction in directions(offer):
        if len(direction.legs) - 1 > max_stops(preferences):
            return False
        if (
            preferences.earliestDepartureHour is not None
            and departs(direction).hour < preferences.earliestDepartureHour
        ):
            return False
    return preferences.cabin is None or all(
        leg.cabin == preferences.cabin for leg in offer.outbound.legs + offer.inbound.legs
    )


def primary_airline(offer: Offer) -> str:
    # Codeshares mix marketing carriers on one flight; the first outbound airline names it.
    leg = offer.outbound.legs[0]
    return leg.airlineCode or leg.airline


def distinct(first: Offer, second: Offer) -> bool:
    return (
        primary_airline(first) != primary_airline(second)
        or stops(first) != stops(second)
        or abs((departs(first.outbound) - departs(second.outbound)).total_seconds()) > 2 * 3600
        or first.outbound.legs[0].origin != second.outbound.legs[0].origin
        or first.cabin != second.cabin
    )


def pick_distinct(
    ordered: Iterable[Offer], chosen: list[Offer] | None = None, limit: int = PICKS
) -> list[Offer]:
    picks = list(chosen or [])
    for offer in ordered:
        if len(picks) >= limit:
            break
        if all(offer.id != pick.id and distinct(offer, pick) for pick in picks):
            picks.append(offer)
    return picks


def value_score(offer: Offer) -> float:
    return offer.totalUsd + HOUR_VALUE_USD * offer.travelers * hours(offer)


def budget_picks(offers: list[Offer], preferences: Preferences, used: set[str]) -> list[Offer]:
    pool = [
        offer
        for offer in offers
        if offer.id not in used
        and suitable(offer, preferences)
        and longest_layover(offer) <= MAX_LAYOVER_MINUTES["budget"]
    ]
    return pick_distinct(sorted(pool, key=lambda offer: (offer.totalUsd, hours(offer))))


def mid_range_pool(offers: list[Offer], preferences: Preferences, used: set[str]) -> list[Offer]:
    """Candidates the model may choose from, best fallback order first."""
    earliest = (
        EARLIEST_HOUR["mid-range"]
        if preferences.earliestDepartureHour is None
        else preferences.earliestDepartureHour
    )
    eligible = [
        offer
        for offer in offers
        if suitable(offer, preferences)
        and offer.cabin == (preferences.cabin or "economy")
        and departs_from(offer, earliest)
        and not airlines(offer) & CARRY_ON_FEE_AIRLINES
    ]
    if not eligible:
        return []
    # The ceiling counts flights Budget already claimed: they still meet the Mid-range rules.
    ceiling = min(offer.totalUsd for offer in eligible) * MID_RANGE_CEILING
    return sorted(
        (o for o in eligible if o.id not in used and o.totalUsd <= ceiling), key=value_score
    )


def mid_range_picks(pool: list[Offer], chosen_ids: list[str] | None) -> list[Offer]:
    """Keep the model's order but never let it add a similar or ineligible option."""
    if chosen_ids is None:
        return pick_distinct(pool)
    by_id = {offer.id: offer for offer in pool}
    return pick_distinct(by_id[offer_id] for offer_id in chosen_ids if offer_id in by_id)


def luxury_picks(
    offers: list[Offer], preferences: Preferences, used: set[str]
) -> tuple[list[Offer], bool]:
    """Return the picks and whether they are economy because no upgrade qualified."""
    earliest = (
        EARLIEST_HOUR["luxury"]
        if preferences.earliestDepartureHour is None
        else preferences.earliestDepartureHour
    )

    def eligible(offer: Offer) -> bool:
        return (
            suitable(offer, preferences) and longest_layover(offer) <= MAX_LAYOVER_MINUTES["luxury"]
        )

    def comfort(offer: Offer) -> tuple[int, int, bool, float]:
        # Better cabin first, then nonstop, then a first departure at the preferred hour.
        return (
            -CABIN_RANK.get(offer.cabin, 0),
            stops(offer),
            not departs_from(offer, earliest),
            offer.totalUsd,
        )

    pool = [offer for offer in offers if offer.id not in used and eligible(offer)]
    if preferences.cabin:
        return pick_distinct(sorted(pool, key=comfort)), False
    economy = [offer for offer in offers if offer.cabin == "economy" and eligible(offer)]
    morning = [offer for offer in economy if departs_from(offer, earliest)]
    fallback = min((offer.totalUsd for offer in morning or economy), default=None)
    same_flights: dict[tuple[str, ...], float] = {}
    for offer in offers:
        if offer.cabin == "economy":
            key = flights(offer)
            same_flights[key] = min(same_flights.get(key, offer.totalUsd), offer.totalUsd)

    def qualifies(offer: Offer) -> bool:
        limit = UPGRADE_LIMIT.get(offer.cabin)
        baseline = same_flights.get(flights(offer), fallback)
        return limit is not None and baseline is not None and offer.totalUsd < limit * baseline

    upgrades = sorted((offer for offer in pool if qualifies(offer)), key=comfort)
    if upgrades:
        # When both cabins qualify, both appear among the picks.
        seeds = [
            best
            for cabin in ("business", "premium_economy")
            if (best := next((o for o in upgrades if o.cabin == cabin), None))
        ]
        return pick_distinct(upgrades, chosen=seeds), False
    economy_pool = [offer for offer in pool if offer.cabin == "economy"]
    return pick_distinct(
        sorted(
            economy_pool,
            key=lambda o: (stops(o), not departs_from(o, earliest), hours(o), o.totalUsd),
        )
    ), True


def usd(amount: float) -> str:
    return f"${amount:,.0f}"


def upgrade_note(offers: list[Offer], pick: Offer) -> str:
    """Only prices already in the search results; never estimate an upgrade."""
    parts = [
        f"{CABIN_NAMES[cabin]} from +{usd(price - pick.totalUsd)}"
        for cabin in ("premium_economy", "business")
        if (price := min((o.totalUsd for o in offers if o.cabin == cabin), default=None))
        and price > pick.totalUsd
    ]
    note = "No upgrade met the value limit."
    return f"{note} {'; '.join(parts)}." if parts else note


def default_reason(category: Category, offer: Offer) -> str:
    count = stops(offer)
    route = (
        "Nonstop both ways" if count == 0 else f"{count} stop{'s' if count > 1 else ''} in total"
    )
    travel = f"about {round(hours(offer))} hours of flying round trip"
    if category == "budget":
        return f"Among the lowest prices found. {route}, {travel}."
    if category == "mid-range":
        return f"Balances price and travel time. {route}, {travel}."
    return f"{CABIN_NAMES.get(offer.cabin, offer.cabin)}. {route}, {travel}."


def recommendation(
    category: Category,
    offer: Offer,
    rationale: str,
    budget: float | None,
    *,
    carry_on: bool = False,
    note: str | None = None,
) -> Recommendation:
    difference = round(max(0, offer.totalUsd - budget), 2) if budget else 0
    return Recommendation(
        category=category,
        offerId=offer.id,
        rationale=rationale,
        overBudgetUsd=difference,
        overBudgetPercent=round(difference / budget * 100, 1) if budget else 0,
        carryOn="likely" if carry_on else None,
        upgradeNote=note,
    )


def refresh_budget(
    recommendations: list[Recommendation], offers: list[Offer], budget: float | None
) -> list[Recommendation]:
    """A budget change only changes over-budget figures; it never reshuffles picks."""
    prices = {offer.id: offer.totalUsd for offer in offers}
    refreshed = []
    for item in recommendations:
        if item.offerId not in prices:
            continue
        difference = round(max(0, prices[item.offerId] - budget), 2) if budget else 0
        refreshed.append(
            item.model_copy(
                update={
                    "overBudgetUsd": difference,
                    "overBudgetPercent": round(difference / budget * 100, 1) if budget else 0,
                }
            )
        )
    return refreshed


def trace_picks(category: Category, picks: list[Offer], offers: list[Offer], source: str) -> None:
    trace = current_trace()
    if not trace:
        return
    baseline = min((offer.totalUsd for offer in offers), default=0)
    first = picks[0] if picks else None
    trace.event(
        "flight_results_ranked",
        policy_version=POLICY_VERSION,
        category=category,
        pick_count=len(picks),
        source=source,
        cabin=first.cabin if first else None,
        # Relative figures only: never emit fares.
        relative_price=round(first.totalUsd / baseline, 3) if first and baseline else None,
        duration_minutes=sum(d.durationMinutes for d in directions(first)) if first else None,
        stops=stops(first) if first else None,
        earliest_hour_rule=EARLIEST_HOUR.get(category),
    )
