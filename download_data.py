#!/usr/bin/env python3
"""
Download NYC 311 road-surface complaint data from NYC Open Data (Socrata API).

Covers two datasets:
  - 76ig-c548: 311 Service Requests from 2010 to 2019
  - erm2-nwe9: 311 Service Requests from 2020 to Present

Two series are downloaded into a single table with a `series` column:

  series='pothole'  — descriptor LIKE '%Pothole%'
                      + 'Rough, Pitted or Cracked Roads' (pitted = early-stage pothole)
    Street Condition / Pothole            (~881K rows)  <- primary forecast target
    Highway Condition / Pothole - Highway (~34K rows)
    Bridge Condition / Pothole            (~3K rows)
    Tunnel Condition / Pothole - Tunnel   (~35 rows)
    Street Condition / Rough, Pitted...   (~72K rows)

  series='cave_in'  — descriptor = 'Cave-in'
    Street/Highway/DEP Condition / Cave-in (~168K rows) <- appendix comparison series

Strategy: iterate year-by-year rather than using large $offsets.
  - Keeps each query small (<=~80K rows/year) - avoids Socrata timeouts
  - Progress is tracked per (series, source_dataset, year) for reliable resumption

Stores results in DuckDB at data/nyc_311_road_surface.duckdb.
"""

import os
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

import duckdb
import pandas as pd  # type: ignore[import-untyped]
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")
API_KEY_ID = os.getenv("SOCRATA_API_KEY_ID")
API_KEY_SECRET = os.getenv("SOCRATA_API_KEY_SECRET")


class DatasetConfig(TypedDict):
    id: str
    label: str
    years: range


# Source datasets and their year ranges
DATASETS: list[DatasetConfig] = [
    {"id": "76ig-c548", "label": "2010-2019", "years": range(2010, 2020)},
    {
        "id": "erm2-nwe9",
        "label": "2020-present",
        "years": range(2020, datetime.now(tz=UTC).date().year + 1),
    },
]

# Series definitions
# Excluded: "Failed Street Repair" - ambiguous; includes utility-cut failures
SERIES = {
    "pothole": (
        "upper(descriptor) like '%POTHOLE%'"
        " OR descriptor = 'Rough, Pitted or Cracked Roads'"
    ),
    "cave_in": "descriptor = 'Cave-in'",
}

BASE_URL = "https://data.cityofnewyork.us/resource/{dataset_id}.json"
BATCH_SIZE = 50_000
DB_PATH = Path("data/nyc_311_road_surface.duckdb")

COLUMNS = [
    "unique_key",
    "created_date",
    "closed_date",
    "complaint_type",
    "descriptor",
    "borough",
    "incident_zip",
    "status",
    "latitude",
    "longitude",
]

CREATE_COMPLAINTS_SQL = """
CREATE TABLE IF NOT EXISTS complaints (
    unique_key      VARCHAR,
    created_date    TIMESTAMPTZ,
    closed_date     TIMESTAMPTZ,
    complaint_type  VARCHAR,
    descriptor      VARCHAR,
    borough         VARCHAR,
    incident_zip    VARCHAR,
    status          VARCHAR,
    latitude        DOUBLE,
    longitude       DOUBLE,
    series          VARCHAR,
    source_dataset  VARCHAR
);
"""

CREATE_PROGRESS_SQL = """
CREATE TABLE IF NOT EXISTS download_progress (
    series         VARCHAR,
    source_dataset VARCHAR,
    year           INTEGER,
    row_count      INTEGER,
    completed_at   TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (series, source_dataset, year)
);
"""


def build_session() -> requests.Session:
    s = requests.Session()
    if APP_TOKEN:
        s.headers["X-App-Token"] = APP_TOKEN
    if API_KEY_ID and API_KEY_SECRET:
        s.auth = (API_KEY_ID, API_KEY_SECRET)
    return s


def fetch_batch(
    session: requests.Session, dataset_id: str, where: str, year: int, offset: int
) -> list[dict]:
    url = BASE_URL.format(dataset_id=dataset_id)
    year_filter = (
        f"created_date >= '{year}-01-01T00:00:00'"
        f" AND created_date < '{year + 1}-01-01T00:00:00'"
    )
    params: dict[str, str | int] = {
        "$where": f"({where}) AND ({year_filter})",
        "$select": ",".join(COLUMNS),
        "$limit": BATCH_SIZE,
        "$offset": offset,
        "$order": "created_date ASC",
    }
    for attempt in range(1, 6):
        try:
            resp = session.get(url, params=params, timeout=180)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == 5:
                raise
            wait = 2**attempt
            print(f"    Retry {attempt}/5: {exc} (waiting {wait}s)")
            time.sleep(wait)
    return []


def batch_to_df(records: list[dict], series: str, source_dataset: str) -> pd.DataFrame:
    df = pd.DataFrame(records)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[COLUMNS].copy()
    for col in ("created_date", "closed_date"):
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    for col in ("latitude", "longitude"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["series"] = series
    df["source_dataset"] = source_dataset
    return df


def is_year_complete(
    con: duckdb.DuckDBPyConnection, series: str, dataset_id: str, year: int
) -> bool:
    row = con.execute(
        "SELECT 1 FROM download_progress WHERE series=? AND source_dataset=? AND year=?",
        [series, dataset_id, year],
    ).fetchone()
    return row is not None


def mark_year_complete(
    con: duckdb.DuckDBPyConnection, series: str, dataset_id: str, year: int, count: int
) -> None:
    con.execute(
        "INSERT OR REPLACE INTO download_progress (series, source_dataset, year, row_count) VALUES (?,?,?,?)",
        [series, dataset_id, year, count],
    )


def fetch_scalar_int(
    con: duckdb.DuckDBPyConnection,
    query: str,
    params: Sequence[object] | None = None,
) -> int:
    row = con.execute(query, params or []).fetchone()
    return int(row[0]) if row else 0


def download_year(
    session: requests.Session,
    con: duckdb.DuckDBPyConnection,
    series: str,
    where: str,
    dataset_id: str,
    year: int,
) -> int:
    offset = 0
    total = 0

    while True:
        records = fetch_batch(session, dataset_id, where, year, offset)
        if not records:
            break

        con.register("batch_df", batch_to_df(records, series, dataset_id))
        con.execute("INSERT INTO complaints SELECT * FROM batch_df")
        con.unregister("batch_df")

        count = len(records)
        total += count
        offset += BATCH_SIZE

        if count < BATCH_SIZE:
            break

    return total


def clear_all(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("DELETE FROM complaints")
    con.execute("DELETE FROM download_progress")


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute(CREATE_COMPLAINTS_SQL)
    con.execute(CREATE_PROGRESS_SQL)

    # Migrate old schema if needed
    cols = [r[0] for r in con.execute("DESCRIBE complaints").fetchall()]
    if "source_dataset" not in cols:
        con.execute("ALTER TABLE complaints ADD COLUMN source_dataset VARCHAR")
        print("Migrated schema: added source_dataset column")

    # Show current state
    existing = fetch_scalar_int(con, "SELECT COUNT(*) FROM complaints")
    completed_years = fetch_scalar_int(con, "SELECT COUNT(*) FROM download_progress")

    if existing > 0:
        progress = con.execute("""
            SELECT series, source_dataset, COUNT(*) AS years_done,
                   SUM(row_count) AS rows_saved
            FROM download_progress
            GROUP BY series, source_dataset
            ORDER BY series, source_dataset
        """).fetchdf()
        print(f"Database: {existing:,} rows, {completed_years} completed year-chunks")
        print(progress.to_string(index=False))
        answer = input("\n  [r] resume   [f] start fresh   [q] quit: ").strip().lower()
        if answer == "q":
            con.close()
            return
        if answer == "f":
            clear_all(con)
            print("Cleared. Starting fresh.\n")

    # Download
    session = build_session()
    grand_total = 0

    for dataset in DATASETS:
        dataset_id = dataset["id"]
        print(f"\nDataset {dataset_id} ({dataset['label']})")

        for series, where in SERIES.items():
            series_total = 0

            for year in dataset["years"]:
                if is_year_complete(con, series, dataset_id, year):
                    saved = fetch_scalar_int(
                        con,
                        "SELECT row_count FROM download_progress WHERE series=? AND source_dataset=? AND year=?",
                        [series, dataset_id, year],
                    )
                    print(
                        f"    [{series}] {year} - skipped (already have {saved:,} rows)"
                    )
                    series_total += saved
                    continue

                # Delete any partial rows for this year before re-downloading
                con.execute(
                    "DELETE FROM complaints WHERE series=? AND source_dataset=? "
                    "AND year(created_date) = ?",
                    [series, dataset_id, year],
                )

                print(f"    [{series}] {year} ...", end=" ", flush=True)
                count = download_year(session, con, series, where, dataset_id, year)
                mark_year_complete(con, series, dataset_id, year, count)
                series_total += count
                print(f"{count:,} rows")

            print(f"    {series}: {series_total:,} total rows")
            grand_total += series_total

    # Deduplicate boundary overlap between datasets
    print("\nDeduplicating by (unique_key, series) ...", end=" ", flush=True)
    con.execute("""
        CREATE TABLE complaints_deduped AS
        SELECT DISTINCT ON (unique_key, series) *
        FROM complaints
        ORDER BY unique_key, series, created_date
    """)
    final_count = fetch_scalar_int(con, "SELECT COUNT(*) FROM complaints_deduped")
    con.execute("DROP TABLE complaints")
    con.execute("ALTER TABLE complaints_deduped RENAME TO complaints")
    print(
        f"done  ({grand_total - final_count:,} duplicates removed, {final_count:,} rows kept)"
    )

    con.close()
    print(f"\nDone! Data saved to {DB_PATH}")
    print("    Example query:")
    print("      SELECT date_trunc('month', created_date) AS month, COUNT(*) AS n")
    print("      FROM complaints WHERE series = 'pothole'")
    print("      GROUP BY month ORDER BY month;")


if __name__ == "__main__":
    main()
