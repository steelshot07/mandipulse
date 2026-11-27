"""v1 commodities and markets, with every name the source has used for each market.

data.gov.in renamed most mandis from Nov 2025 ("Lasalgaon" -> "Lasalgaon APMC" ->
"APMC Lasalgaon "), and some districts were split ("Chittor" -> "Annamayya"). A market is
matched by (state, normalised name), so a series survives these changes. ``districts``
lists every district the market has been filed under; it is only used to narrow the API
query. Names here are matched after strip + casefold, so trailing spaces don't matter.
"""

from dataclasses import dataclass
from datetime import date

BACKFILL_START = date(2019, 1, 1)


@dataclass(frozen=True)
class CommodityConfig:
    slug: str
    name: str  # exactly as the source spells it


@dataclass(frozen=True)
class MarketConfig:
    slug: str
    market_name: str  # display name
    state: str  # exactly as the source spells it
    districts: tuple[str, ...]  # current district first
    aliases: tuple[str, ...]  # source market names, any order
    commodities: tuple[str, ...]  # commodity slugs tracked at this market


COMMODITIES: tuple[CommodityConfig, ...] = (
    CommodityConfig("onion", "Onion"),
    CommodityConfig("tomato", "Tomato"),
    CommodityConfig("potato", "Potato"),
)

_MH = "Maharashtra"
_NASHIK = ("Nashik",)

MARKETS: tuple[MarketConfig, ...] = (
    # --- Onion ---
    MarketConfig(
        "lasalgaon",
        "Lasalgaon",
        _MH,
        _NASHIK,
        ("Lasalgaon", "Lasalgaon APMC", "APMC Lasalgaon"),
        ("onion",),
    ),
    MarketConfig(
        "lasalgaon-niphad",
        "Lasalgaon (Niphad)",
        _MH,
        _NASHIK,
        ("Lasalgaon(Niphad)", "Lasalgaon(Niphad) APMC"),
        ("onion",),
    ),
    MarketConfig(
        "lasalgaon-vinchur",
        "Lasalgaon (Vinchur)",
        _MH,
        _NASHIK,
        ("Lasalgaon(Vinchur)", "Lasalgaon(Vinchur) APMC"),
        ("onion",),
    ),
    MarketConfig(
        "pimpalgaon-baswant",
        "Pimpalgaon Baswant",
        _MH,
        _NASHIK,
        (
            "Pimpalgaon",
            "Pimpalgaon APMC",
            "Pimpalgaon Baswant APMC",
            "APMC Pimpalgaon Baswant",
        ),
        ("onion",),
    ),
    MarketConfig(
        "pimpalgaon-saykheda",
        "Pimpalgaon (Saykheda)",
        _MH,
        _NASHIK,
        ("Pimpalgaon Baswant(Saykheda)", "Pimpalgaon Baswant(Saykheda) APMC"),
        ("onion",),
    ),
    MarketConfig(
        "nashik",
        "Nashik",
        _MH,
        _NASHIK,
        ("Nasik", "Nasik APMC", "APMC Nasik"),
        ("onion",),
    ),
    MarketConfig(
        "manmad",
        "Manmad",
        _MH,
        _NASHIK,
        ("Manmad", "Manmad APMC", "APMC Manmad"),
        ("onion",),
    ),
    MarketConfig(
        "mandsaur",
        "Mandsaur",
        "Madhya Pradesh",
        ("Mandsaur",),
        ("Mandsaur", "Mandsaur APMC"),
        ("onion",),
    ),
    MarketConfig(
        "bengaluru",
        "Bengaluru",
        "Karnataka",
        ("Bengaluru", "Bangalore"),
        ("Bangalore", "Bangalore APMC", "Bengaluru APMC"),
        ("onion",),
    ),
    # --- Tomato ---
    MarketConfig(
        "kolar",
        "Kolar",
        "Karnataka",
        ("Kolar",),
        ("Kolar", "Kolar APMC"),
        ("tomato",),
    ),
    MarketConfig(
        "chintamani",
        "Chintamani",
        "Karnataka",
        ("Chikkaballapur", "Kolar"),
        ("Chintamani", "Chintamani APMC"),
        ("tomato",),
    ),
    MarketConfig(
        "madanapalle",
        "Madanapalle",
        "Andhra Pradesh",
        ("Annamayya", "Chittor"),
        ("Madanapalli", "Madanapalli APMC"),
        ("tomato",),
    ),
    MarketConfig(
        "kalikiri",
        "Kalikiri",
        "Andhra Pradesh",
        ("Annamayya", "Chittor"),
        ("Kalikiri", "Kalikiri APMC"),
        ("tomato",),
    ),
    # --- Tomato + Potato ---
    MarketConfig(
        "azadpur",
        "Azadpur (Delhi)",
        "NCT of Delhi",
        ("Delhi",),
        ("Azadpur", "Azadpur APMC", "APMC Azadpur"),
        ("tomato", "potato"),
    ),
    # --- Potato ---
    MarketConfig(
        "agra",
        "Agra",
        "Uttar Pradesh",
        ("Agra",),
        ("Agra", "Agra APMC"),
        ("potato",),
    ),
    MarketConfig(
        "kolkata-bara-bazar",
        "Kolkata (Bara Bazar)",
        "West Bengal",
        ("Kolkata",),
        ("Bara Bazar (Posta Bazar)", "Bara Bazar (Posta Bazar) APMC"),
        ("potato",),
    ),
)


# Approximate mandi locations (lat, lon in degrees), read off public maps. Used to pick the
# IMD rainfall grid cells around each mandi; +/- a few km doesn't matter on a 0.25 deg grid.
MARKET_COORDS: dict[str, tuple[float, float]] = {
    "lasalgaon": (20.150, 74.233),
    "lasalgaon-niphad": (20.080, 74.110),
    "lasalgaon-vinchur": (20.112, 74.218),
    "pimpalgaon-baswant": (20.167, 73.988),
    "pimpalgaon-saykheda": (20.040, 73.990),
    "nashik": (19.997, 73.790),
    "manmad": (20.252, 74.437),
    "mandsaur": (24.076, 75.069),
    "bengaluru": (13.030, 77.540),
    "kolar": (13.137, 78.129),
    "chintamani": (13.401, 78.057),
    "madanapalle": (13.551, 78.503),
    "kalikiri": (13.633, 78.800),
    "azadpur": (28.708, 77.176),
    "agra": (27.177, 78.008),
    "kolkata-bara-bazar": (22.585, 88.354),
}


def normalise(name: str) -> str:
    """Normalise a source name for matching: trim, collapse inner spaces, casefold."""
    return " ".join(name.split()).casefold()


def alias_index() -> dict[tuple[str, str], MarketConfig]:
    """Map (normalised state, normalised source market name) -> market config."""
    index: dict[tuple[str, str], MarketConfig] = {}
    for market in MARKETS:
        for alias in market.aliases:
            key = (normalise(market.state), normalise(alias))
            if key in index:
                raise ValueError(f"alias {alias!r} is used by {index[key].slug} and {market.slug}")
            index[key] = market
    return index


def fetch_plan() -> list[tuple[CommodityConfig, str, str]]:
    """Distinct (commodity, state, district) API queries needed to cover all markets."""
    by_slug = {c.slug: c for c in COMMODITIES}
    plan: dict[tuple[str, str, str], CommodityConfig] = {}
    for market in MARKETS:
        for slug in market.commodities:
            for district in market.districts:
                plan.setdefault((slug, market.state, district), by_slug[slug])
    return [(commodity, state, district) for (_, state, district), commodity in plan.items()]
