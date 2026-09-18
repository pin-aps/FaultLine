import requests
import pandas as pd
from pathlib import Path
import time

BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"

CA_BOUNDS = {
    "minlatitude": 32.0,
    "maxlatitude": 42.5,
    "minlongitude": -125.0,
    "maxlongitude": -113.5,
}

def fetch_one_quarter(year, quarter, min_magnitude=1.5):
    """
    Fetches one quarter of one year at a time.
    Chose this so i dont hit 20,000 event limit and so that requests are smaller and less likely to time out.
    """
    quarter_starts = ["01-01", "04-01", "07-01", "10-01"]
    quarter_ends   = ["04-01", "07-01", "10-01", "01-01"]

    start = f"{year}-{quarter_starts[quarter]}"
    # Q4 ends roll into the next year
    end_year = year + 1 if quarter == 3 else year
    end = f"{end_year}-{quarter_ends[quarter]}"

    params = {
        "format":       "geojson",
        "starttime":    start,
        "endtime":      end,
        "minmagnitude": min_magnitude,
        **CA_BOUNDS,
        "orderby":      "time",
        "limit":        20000,
    }

    response = requests.get(BASE_URL, params=params, timeout=60)

#error catch if api is rejected due to too many requests or other issues. This will print the first 500 characters of the error message for debugging.
    if response.status_code == 400:
        print(f"\nAPI rejected request. Response body:")
        print(response.text[:500])  # first 500 chars of error message
        response.raise_for_status()

    response.raise_for_status()

    features = response.json()["features"]

#records is a list of dictionaries, each representing an earthquake event with relevant properties extracted from the API response. 
# The function returns a pandas DataFrame constructed from this list of records.
    records = []
    for f in features:
        p = f["properties"]
        coords = f["geometry"]["coordinates"]
        records.append({
            "event_id":  f["id"],
            "time":      pd.to_datetime(p["time"], unit="ms", utc=True),
            "latitude":  coords[1],
            "longitude": coords[0],
            "depth_km":  coords[2],
            "magnitude": p["mag"],
            "mag_type":  p["magType"],
            "place":     p["place"],
            "status":    p["status"],
        })

    return pd.DataFrame(records)


#function to fetch all years of data from the USGS API, iterating through each year and quarter, and concatenating the results into a single DataFrame. 
# It also prints summary statistics about the fetched data.
def fetch_all_years(start_year=2016, end_year=2026, min_magnitude=1.5):
    all_dfs = []
    total = 0

    print(f"Fetching USGS data {start_year}–{end_year}, M>={min_magnitude}")
    for year in range(start_year, end_year):
        year_dfs = []
        for q in range(4):
            print(f"  {year} Q{q+1}...", end=" ", flush=True)
            df = fetch_one_quarter(year, q, min_magnitude)
            print(f"{len(df):,} events")
            year_dfs.append(df)
            time.sleep(0.5)  

        year_df = pd.concat(year_dfs, ignore_index=True)
        total += len(year_df)
        all_dfs.append(year_df)

    combined = pd.concat(all_dfs, ignore_index=True)
    combined = combined.drop_duplicates(subset="event_id")
    combined = combined.sort_values("time").reset_index(drop=True)

    print(f"\nTotal events: {len(combined):,}")
    print(f"Date range: {combined['time'].min().date()} to {combined['time'].max().date()}")
    print(f"Magnitude range: M{combined['magnitude'].min():.1f} – M{combined['magnitude'].max():.1f}")

    return combined


if __name__ == "__main__":
    # First do a quick single test request before running the full fetch
    # This way you know the API is responding before committing to 10 years
    print("Testing API with single small request...")
    test = fetch_one_quarter(2020, 0, min_magnitude=2.5)
    print(f"Test passed — got {len(test):,} events for 2020 Q1 M>=2.5\n")

    # Now run the full fetch
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    df = fetch_all_years(start_year=2016, end_year=2026)

    out_path = Path("data/raw/usgs_2016_2026.parquet")
    df.to_parquet(out_path, index=False)
    print(f"Saved to {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")