"""/meta, /prices and /analytics routes: happy path + errors (services replaced by fakes)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.routes.data import get_analytics_service, get_price_service
from app.main import create_app
from app.schemas.analytics import LagCorrelation, MarketVolatility, SeasonalityCell
from app.schemas.prices import PricePoint
from app.services.analytics import AnalyticsService, lag_correlation, month_profile
from app.services.prices import PriceService


class FakePrices(PriceService):
    def __init__(self) -> None:
        super().__init__(None)
        self.calls: list[tuple[str, str, str, date, date]] = []

    def last_arrival_date(self, commodity: str, market: str) -> date | None:
        return date(2026, 11, 26)

    def series(
        self, commodity: str, market: str, freq: str, start: date, end: date
    ) -> list[PricePoint]:
        self.calls.append((commodity, market, freq, start, end))
        return [
            PricePoint(
                date=date(2026, 11, 16),
                modal_price=4300,
                min_price=1000,
                max_price=5000,
                n_reports=9,
            ),
            PricePoint(
                date=date(2026, 11, 23),
                modal_price=None,
                min_price=None,
                max_price=None,
                n_reports=0,
                is_gap=True,
                modal_price_filled=4300,
            ),
        ]


class FakeAnalytics(AnalyticsService):
    def __init__(self) -> None:
        super().__init__(None)

    def volatility(self, commodity: str) -> list[MarketVolatility]:
        return [
            MarketVolatility(
                market="lasalgaon",
                market_name="Lasalgaon",
                cv_52w=0.55,
                cv_all=0.7,
                mean_abs_weekly_change_52w=0.08,
                rolling_std_4w=120.0,
                last_week=date(2026, 11, 23),
            )
        ]

    def seasonality(self, commodity: str, market: str) -> list[SeasonalityCell]:
        return [
            SeasonalityCell(
                year=2025, month=m, avg_price=1000 + m, index_vs_year_avg=1.0, n_weeks=4
            )
            for m in range(1, 13)
        ]

    def rainfall_impact(self, commodity: str, market: str) -> list[LagCorrelation]:
        return [lag_correlation(0, -0.3, 300), lag_correlation(1, 0.05, 300)]


@pytest.fixture
def prices() -> FakePrices:
    return FakePrices()


@pytest.fixture
def client(prices: FakePrices) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_price_service] = lambda: prices
    app.dependency_overrides[get_analytics_service] = FakeAnalytics
    return TestClient(app)


# --- /meta ---


def test_meta_commodities(client: TestClient) -> None:
    body = client.get("/meta/commodities").json()
    assert {c["slug"]: c["market_count"] for c in body} == {"onion": 9, "tomato": 5, "potato": 3}


def test_meta_markets_filtered(client: TestClient) -> None:
    body = client.get("/meta/markets", params={"commodity": "potato"}).json()
    assert {m["slug"] for m in body} == {"agra", "azadpur", "kolkata-bara-bazar"}
    assert all(m["lat"] and m["lon"] for m in body)


def test_meta_markets_unknown_commodity(client: TestClient) -> None:
    resp = client.get("/meta/markets", params={"commodity": "garlic"})
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "not_found"


# --- /prices ---


def test_prices_weekly(client: TestClient, prices: FakePrices) -> None:
    resp = client.get("/prices", params={"commodity": "onion", "market": "lasalgaon"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["freq"] == "weekly" and body["unit"] == "₹/quintal"
    assert body["points"][1]["is_gap"] and body["points"][1]["modal_price_filled"] == 4300
    assert resp.headers["Cache-Control"] == "public, max-age=300"
    assert prices.calls[0][2] == "weekly"


def test_prices_daily_with_range(client: TestClient, prices: FakePrices) -> None:
    params = {
        "commodity": "tomato",
        "market": "kolar",
        "freq": "daily",
        "from": "2026-01-01",
        "to": "2026-02-01",
    }
    assert client.get("/prices", params=params).status_code == 200
    assert prices.calls[0][2:] == ("daily", date(2026, 1, 1), date(2026, 2, 1))


@pytest.mark.parametrize(
    ("params", "status", "code"),
    [
        ({"commodity": "onion", "market": "kolar"}, 404, "not_found"),  # not tracked
        ({"commodity": "onion", "market": "nowhere"}, 404, "not_found"),
        ({"commodity": "onion"}, 400, "bad_request"),  # market missing
        ({"commodity": "ON;ION", "market": "lasalgaon"}, 400, "bad_request"),
        ({"commodity": "onion", "market": "lasalgaon", "freq": "hourly"}, 400, "bad_request"),
        (
            {"commodity": "onion", "market": "lasalgaon", "from": "2026-02-01", "to": "2026-01-01"},
            400,
            "bad_request",
        ),
        (
            {
                "commodity": "onion",
                "market": "lasalgaon",
                "freq": "daily",
                "from": "2019-01-01",
                "to": "2026-01-01",
            },
            400,
            "bad_request",
        ),
    ],
)
def test_prices_errors(client: TestClient, params: dict[str, str], status: int, code: str) -> None:
    resp = client.get("/prices", params=params)
    assert resp.status_code == status
    assert resp.json()["error"]["code"] == code


# --- /analytics ---


def test_volatility(client: TestClient) -> None:
    body = client.get("/analytics/volatility", params={"commodity": "onion"}).json()
    assert body["markets"][0]["cv_52w"] == 0.55


def test_volatility_unknown_commodity(client: TestClient) -> None:
    assert client.get("/analytics/volatility", params={"commodity": "rice"}).status_code == 404


def test_seasonality_includes_profile(client: TestClient) -> None:
    body = client.get(
        "/analytics/seasonality", params={"commodity": "onion", "market": "nashik"}
    ).json()
    assert len(body["cells"]) == 12 and len(body["profile"]) == 12


def test_seasonality_wrong_market(client: TestClient) -> None:
    resp = client.get("/analytics/seasonality", params={"commodity": "potato", "market": "kolar"})
    assert resp.status_code == 404


def test_rainfall_impact(client: TestClient) -> None:
    body = client.get(
        "/analytics/rainfall-impact", params={"commodity": "onion", "market": "lasalgaon"}
    ).json()
    assert [lag["significant"] for lag in body["lags"]] == [True, False]
    assert "normal" in body["rainfall_measure"]


def test_rainfall_impact_missing_market(client: TestClient) -> None:
    resp = client.get("/analytics/rainfall-impact", params={"commodity": "onion"})
    assert resp.status_code == 400


# --- pure helpers ---


def test_month_profile_uses_only_complete_years() -> None:
    cells = [
        SeasonalityCell(year=2024, month=m, avg_price=1, index_vs_year_avg=2.0, n_weeks=4)
        for m in range(1, 13)
    ]
    cells.append(SeasonalityCell(year=2025, month=1, avg_price=1, index_vs_year_avg=9.0, n_weeks=4))
    profile = month_profile(cells)
    assert profile[0].avg_index == 2.0 and profile[0].n_years == 1


def test_lag_correlation_significance_threshold() -> None:
    assert lag_correlation(0, 0.12, 300).significant  # 1.96/sqrt(300) = 0.113
    assert not lag_correlation(0, 0.10, 300).significant
    assert not lag_correlation(0, None, 0).significant
