"""Daily job window and argument validation."""

from datetime import date

import pytest

from ingestion.run_daily import main, since_for


def test_window_includes_today_and_covers_n_days() -> None:
    assert since_for(date(2026, 11, 26), 10) == date(2026, 11, 17)
    assert since_for(date(2026, 11, 26), 1) == date(2026, 11, 26)


@pytest.mark.parametrize("days", ["0", "61", "abc"])
def test_rejects_out_of_range_days(days: str) -> None:
    with pytest.raises(SystemExit):
        main(["--days", days])
