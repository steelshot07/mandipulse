"""Per-row validation of data.gov.in mandi price records."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

PositivePrice = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


class DataGovPriceRecord(BaseModel):
    """One row of the 'Variety-wise Daily Market Prices' resource.

    Old rows send prices as strings and new rows as numbers; both are accepted.
    Names are stripped because the source has trailing spaces (e.g. 'APMC Lasalgaon ').
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore", frozen=True)

    state: Annotated[str, Field(alias="State", min_length=1)]
    district: Annotated[str, Field(alias="District", min_length=1)]
    market: Annotated[str, Field(alias="Market", min_length=1)]
    commodity: Annotated[str, Field(alias="Commodity", min_length=1)]
    variety: Annotated[str, Field(alias="Variety", min_length=1)]
    grade: Annotated[str, Field(alias="Grade", min_length=1)]
    arrival_date: Annotated[date, Field(alias="Arrival_Date")]
    min_price: Annotated[PositivePrice, Field(alias="Min_Price")]
    max_price: Annotated[PositivePrice, Field(alias="Max_Price")]
    modal_price: Annotated[PositivePrice, Field(alias="Modal_Price")]

    @field_validator("arrival_date", mode="before")
    @classmethod
    def _parse_ddmmyyyy(cls, value: object) -> object:
        """The source uses dd/mm/yyyy."""
        if isinstance(value, str):
            return datetime.strptime(value.strip(), "%d/%m/%Y").date()
        return value
