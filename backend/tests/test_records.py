"""Validation of single data.gov.in price rows."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from ingestion.records import DataGovPriceRecord


def row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "State": "Maharashtra",
        "District": "Nashik",
        "Market": "APMC Lasalgaon ",
        "Commodity": "Onion",
        "Commodity_Code": "23",
        "Variety": "Red",
        "Grade": "FAQ",
        "Arrival_Date": "05/11/2025",
        "Min_Price": "1000",
        "Max_Price": "2500",
        "Modal_Price": "2100",
    }
    base.update(overrides)
    return base


def test_parses_string_prices_and_ddmmyyyy_date() -> None:
    rec = DataGovPriceRecord.model_validate(row())
    assert rec.arrival_date == date(2025, 11, 5)
    assert rec.modal_price == Decimal("2100")
    assert rec.market == "APMC Lasalgaon"  # trailing space stripped


def test_accepts_numeric_prices() -> None:
    rec = DataGovPriceRecord.model_validate(row(Min_Price=1000, Max_Price=2500.5, Modal_Price=2100))
    assert rec.max_price == Decimal("2500.5")


@pytest.mark.parametrize(
    "overrides",
    [
        {"Modal_Price": "0"},
        {"Min_Price": "-5"},
        {"Max_Price": "abc"},
        {"Arrival_Date": "2025-11-05"},
        {"Market": "  "},
        {"Variety": None},
    ],
)
def test_rejects_bad_rows(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DataGovPriceRecord.model_validate(row(**overrides))
