"""Consistency checks on the v1 market config."""

from app.core.markets import COMMODITIES, MARKETS, alias_index, fetch_plan, normalise


def test_slugs_unique_and_commodities_known() -> None:
    slugs = [m.slug for m in MARKETS]
    assert len(slugs) == len(set(slugs))
    known = {c.slug for c in COMMODITIES}
    for m in MARKETS:
        assert m.commodities and set(m.commodities) <= known, m.slug
        assert m.districts and m.aliases, m.slug


def test_aliases_unique_within_state() -> None:
    index = alias_index()  # raises on a clash
    assert index[(normalise("Maharashtra"), normalise("APMC Lasalgaon "))].slug == "lasalgaon"
    assert index[(normalise("Karnataka"), normalise("Bangalore"))].slug == "bengaluru"


def test_normalise_ignores_case_and_spacing() -> None:
    assert normalise("  APMC   Lasalgaon ") == "apmc lasalgaon"


def test_fetch_plan_covers_every_market_district() -> None:
    plan = {(c.slug, state, district) for c, state, district in fetch_plan()}
    for m in MARKETS:
        for slug in m.commodities:
            for district in m.districts:
                assert (slug, m.state, district) in plan
    assert len(plan) == len(fetch_plan())  # no duplicate queries
