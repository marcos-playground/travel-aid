"""Initial, deliberately tunable category policy. No model-generated price or cabin claims."""

from datetime import datetime

from travel_aid.observability import current_trace
from travel_aid.planning.models import Cabin, Offer, Preferences, Recommendation

COMFORT = {"unknown": 0, "mixed": 0.5, "economy": 1, "premium_economy": 2, "business": 3}
# Exploration heuristics, not predicted fares: only expand when the target has headroom
# relative to observed economy quotes. A user can explicitly request a cabin at any budget.
CABIN_HEADROOM: dict[Cabin, float] = {"economy": 1, "premium_economy": 1.4, "business": 2.5}
POLICY_VERSION = "flight-ranking-v1"


def should_search(
    cabin: Cabin, offers: list[Offer], budget: float | None, preferences: Preferences
) -> bool:
    if preferences.cabin:
        return cabin == preferences.cabin
    if cabin == "economy":
        return True
    if not offers:
        return budget is None
    return (
        budget is None or budget * 1.15 >= min(o.totalUsd for o in offers) * CABIN_HEADROOM[cabin]
    )


def suitable(offer: Offer, preferences: Preferences) -> bool:
    for direction in (offer.outbound, offer.inbound):
        if preferences.maxStops is not None and len(direction.legs) - 1 > preferences.maxStops:
            return False
        if (
            preferences.earliestDepartureHour is not None
            and datetime.fromisoformat(direction.legs[0].departsAt).hour
            < preferences.earliestDepartureHour
        ):
            return False
    return preferences.cabin is None or all(
        leg.cabin == preferences.cabin for leg in offer.outbound.legs + offer.inbound.legs
    )


def convenience(offer: Offer) -> float:
    return sum(
        direction.durationMinutes / 60 + (len(direction.legs) - 1) * 3
        for direction in (offer.outbound, offer.inbound)
    )


def rank(
    offers: list[Offer], budget: float | None, preferences: Preferences
) -> list[Recommendation]:
    candidates = [offer for offer in offers if suitable(offer, preferences)]
    if not candidates:
        return []
    baseline = min(o.totalUsd for o in candidates)
    target = budget or baseline
    chosen: list[Recommendation] = []
    used: set[str] = set()
    for category in ("budget", "mid-range", "luxury"):
        available = [o for o in candidates if o.id not in used]
        if category == "mid-range":
            available = [
                o
                for o in available
                if all(
                    datetime.fromisoformat(d.legs[0].departsAt).hour >= 5
                    for d in (o.outbound, o.inbound)
                )
            ]
        if not available:
            continue

        def score(offer: Offer, category: str = category) -> float:
            relative = offer.totalUsd / baseline
            over = max(0, offer.totalUsd / target - 1)
            comfort = COMFORT.get(offer.cabin, 0)
            if category == "budget":
                return offer.totalUsd
            if category == "mid-range":
                return convenience(offer) + relative * 5 + over * 25 - comfort * 2
            return convenience(offer) + relative * 3 + over * 30 - comfort * 9

        best = min(available, key=score)
        used.add(best.id)
        difference = round(max(0, best.totalUsd - budget), 2) if budget else 0
        reasons: dict[str, str] = {
            "budget": "The lowest-priced round trip matching your preferences among these results.",
            "mid-range": (
                "Balances travel time, stops and cabin comfort, with departures at 5 AM or later."
            ),
            "luxury": (
                "Prioritizes cabin comfort while weighing travel time and the cost of upgrading."
            ),
        }
        chosen.append(
            Recommendation(
                category=category,
                offerId=best.id,
                rationale=reasons[category],
                overBudgetUsd=difference,
                overBudgetPercent=round(difference / budget * 100, 1) if budget else 0,
            )
        )
        trace = current_trace()
        if trace:
            trace.event(
                "flight_results_ranked",
                policy_version=POLICY_VERSION,
                category=category,
                cabin=best.cabin,
                # Budget ranking uses dollars internally; emit a relative score only.
                ranking_score=round(
                    score(best) / baseline if category == "budget" else score(best), 3
                ),
                duration_minutes=sum(d.durationMinutes for d in (best.outbound, best.inbound)),
                stops=sum(len(d.legs) - 1 for d in (best.outbound, best.inbound)),
                relative_price=round(best.totalUsd / baseline, 3),
                over_budget_ratio=round(difference / budget, 3) if budget else 0,
                earliest_hour_rule=5 if category == "mid-range" else None,
            )
    return chosen
