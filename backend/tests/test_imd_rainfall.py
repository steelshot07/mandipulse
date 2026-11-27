"""IMD rainfall parsing, box averaging and normals (no network, no database)."""

import io
from datetime import date, timedelta

import httpx
import numpy as np
import pytest
from scipy.io import netcdf_file

from ingestion.imd_rainfall import (
    GRID_LAT,
    GRID_LON,
    MISSING,
    Climatology,
    ImdClient,
    ImdError,
    box_masks,
    box_mean,
    month_day,
    parse_realtime,
    parse_yearly,
    rain_rows,
)

SHAPE = (GRID_LAT.size, GRID_LON.size)


def _cell(lat: float, lon: float) -> tuple[int, int]:
    return int(np.argmin(np.abs(GRID_LAT - lat))), int(np.argmin(np.abs(GRID_LON - lon)))


def test_parse_realtime_is_row_major_lat_lon() -> None:
    grid = np.full(SHAPE, MISSING, dtype="<f4")
    i, j = _cell(20.0, 74.0)
    grid[i, j] = 12.5
    parsed = parse_realtime(grid.tobytes())
    assert parsed.shape == SHAPE and parsed[i, j] == 12.5


def test_parse_realtime_rejects_wrong_size() -> None:
    with pytest.raises(ImdError):
        parse_realtime(b"\x00" * 100)


def test_parse_yearly_netcdf() -> None:
    buf = io.BytesIO()
    nc = netcdf_file(buf, "w")
    nc.createDimension("TIME", 2)
    nc.createDimension("LATITUDE", SHAPE[0])
    nc.createDimension("LONGITUDE", SHAPE[1])
    nc.createVariable("LATITUDE", "d", ("LATITUDE",))[:] = GRID_LAT
    nc.createVariable("LONGITUDE", "d", ("LONGITUDE",))[:] = GRID_LON
    time_var = nc.createVariable("TIME", "d", ("TIME",))
    time_var[:] = [45292.0, 45293.0]  # 2025-01-01, 2025-01-02 (days since 1900-12-31)
    rain = nc.createVariable("RAINFALL", "f", ("TIME", "LATITUDE", "LONGITUDE"))
    rain[:] = np.full((2, *SHAPE), 3.0, dtype="f")
    nc.flush()
    content = buf.getvalue()
    nc.close()

    days, grids = parse_yearly(content)
    assert days == [date(2025, 1, 1), date(2025, 1, 2)]
    assert grids.shape == (2, *SHAPE) and grids[1, 0, 0] == 3.0


def test_box_covers_about_half_a_degree_each_way() -> None:
    mask = box_masks({"x": (20.15, 74.23)})["x"]
    lats = GRID_LAT[mask.any(axis=1)]
    lons = GRID_LON[mask.any(axis=0)]
    assert lats.min() >= 19.65 and lats.max() <= 20.65
    assert lons.min() >= 73.73 and lons.max() <= 74.73
    assert mask.sum() == 16  # 4 x 4 cells on the 0.25 deg grid


def test_box_outside_grid_is_rejected() -> None:
    with pytest.raises(ValueError):
        box_masks({"london": (51.5, -0.1)})


def test_box_mean_ignores_missing_cells() -> None:
    mask = box_masks({"x": (20.15, 74.23)})["x"]
    grid = np.full((1, *SHAPE), MISSING)
    cells = np.argwhere(mask)
    grid[0, cells[0][0], cells[0][1]] = 10.0
    grid[0, cells[1][0], cells[1][1]] = 20.0
    assert box_mean(grid, mask)[0] == 15.0
    assert np.isnan(box_mean(np.full((1, *SHAPE), MISSING), mask)[0])


def test_normals_are_smoothed_and_include_29_feb() -> None:
    clim = Climatology.empty(["x"])
    for year in (2019, 2020):  # 2020 is a leap year
        days = [date(year, 1, 1) + timedelta(days=i) for i in range(366 if year == 2020 else 365)]
        values = np.array([30.0 if d.month == 7 and d.day == 15 else 0.0 for d in days])
        clim.add("x", days, values)
    normals = clim.normals("x")
    assert len(normals) == 366 and 229 in normals
    # The single wet day is spread evenly over the 31-day window.
    assert normals[715] == pytest.approx(30.0 / 31)
    assert normals[630] == pytest.approx(30.0 / 31)
    assert normals[629] == 0.0
    assert sum(normals.values()) == pytest.approx(30.0)


def test_normals_need_every_calendar_day() -> None:
    clim = Climatology.empty(["x"])
    clim.add("x", [date(2021, 1, 1)], np.array([1.0]))
    with pytest.raises(ValueError):
        clim.normals("x")


def test_month_day_key() -> None:
    assert month_day(date(2024, 2, 29)) == 229
    assert month_day(date(2025, 12, 31)) == 1231


def test_rain_rows_store_missing_as_null() -> None:
    rows = rain_rows(1, [date(2026, 1, 1), date(2026, 1, 2)], np.array([1.234, np.nan]), "x")
    assert rows == [(1, date(2026, 1, 1), 1.23, "x"), (1, date(2026, 1, 2), None, "x")]


def test_client_treats_empty_response_as_not_published() -> None:
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.content.decode())
        return httpx.Response(200, content=b"")

    with ImdClient(transport=httpx.MockTransport(handler)) as client:
        assert client.fetch_year(2026) is None
        assert client.fetch_day(date(2026, 11, 20)) is None
    assert seen == ["RF25=2026", "rain=20112026"]


def test_client_retries_server_errors() -> None:
    calls = iter([503, 200])
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        status = next(calls)
        return httpx.Response(status, content=b"" if status == 200 else b"busy")

    with ImdClient(transport=httpx.MockTransport(handler), sleep=sleeps.append) as client:
        assert client.fetch_day(date(2026, 1, 1)) is None
    assert sleeps == [2.0]
