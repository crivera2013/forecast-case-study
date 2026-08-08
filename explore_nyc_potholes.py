# pylint: disable=function-redefined
import os

import marimo
from dotenv import load_dotenv

__generated_with = "0.23.16"
app = marimo.App()

# Load environment variables
load_dotenv()


@app.cell
def _():
    import pandas as pd  # type: ignore[import-untyped]
    import requests

    APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")
    API_KEY_ID = os.getenv("SOCRATA_API_KEY_ID")
    API_KEY_SECRET = os.getenv("SOCRATA_API_KEY_SECRET")

    DATASETS = [
        {"id": "76ig-c548", "label": "2010-2019"},
        {"id": "erm2-nwe9", "label": "2020-present"},
    ]

    BASE_URL = "https://data.cityofnewyork.us/resource/{dataset_id}.json"

    ROAD_COMPLAINT_TYPES = [
        "Street Condition",
        "Highway Condition",
        "Bridge Condition",
        "Tunnel Condition",
    ]

    def keyword_where():
        return "UPPER(complaint_type) LIKE '%CONDITION%' OR UPPER(descriptor) LIKE '%POTHOLE%'"

    def build_session():
        s = requests.Session()
        if APP_TOKEN:
            s.headers["X-App-Token"] = APP_TOKEN
        if API_KEY_ID and API_KEY_SECRET:
            s.auth = (API_KEY_ID, API_KEY_SECRET)
        return s

    return (
        API_KEY_ID,
        API_KEY_SECRET,
        APP_TOKEN,
        BASE_URL,
        DATASETS,
        ROAD_COMPLAINT_TYPES,
        keyword_where,
        build_session,
        pd,
        requests,
    )


@app.cell
def _(BASE_URL, DATASETS, build_session, pd):
    session = build_session()
    frames = []

    for ds in DATASETS:
        print(f"Querying {ds['id']} ({ds['label']})...", flush=True)
        url = BASE_URL.format(dataset_id=ds["id"])

        params = {
            "$select": (
                "agency, complaint_type, descriptor, "
                "count(unique_key) as cnt, "
                "min(created_date) as earliest, "
                "max(created_date) as latest"
            ),
            "$where": "agency='DOT' OR UPPER(complaint_type) LIKE '%CONDITION%'",
            "$group": "agency, complaint_type, descriptor",
            "$order": "cnt DESC",
            "$limit": 1000,
        }

        resp = session.get(url, params=params, timeout=60)
        resp.raise_for_status()
        df = pd.DataFrame(resp.json())
        df.insert(0, "dataset", ds["label"])
        frames.append(df)

    return frames, session


@app.cell
def _(frames, pd):
    pd.concat(frames, ignore_index=True).to_csv("data/complaint_types.csv", index=False)


if __name__ == "__main__":
    app.run()
