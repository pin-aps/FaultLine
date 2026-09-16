import requests
import pandas as pd
from pathlib import Path
import time
import io

# University of Nevada Reno (UNR) Nevada Geodetic Laboratory
# Fully public, no login required, 13,000+ stations worldwide
# IGS14 reference frame — covers up to Aug 2024 (then IGS20 takes over)
# We use IGS14 because it has the longest complete history for our stations
BASE_URL = "https://geodesy.unr.edu/gps_timeseries/IGS14/tenv3/IGS14"

# San Andreas fault GPS stations — all confirmed in UNR's network
STATIONS = {
    "CMBB": "Columbia (N. Sierra)",
    "HOPB": "Hopland",
    "BKMS": "Parkfield",
    "CRFP": "Cholame",
    "COPR": "Carpinteria",
    "TRHS": "Thousand Palms",
    "P495": "Bombay Beach (Salton Sea)",
    "P066": "Gorman (Tejon Pass area)",
    "P506": "Indio (S. San Andreas)",
}


def fetch_station(station_code, station_name):
    """
    Downloads the UNR IGS14 position time series for one GPS station.

    UNR file format (tenv3):
    - Tab-separated, one row per day
    - Columns: site, YYMMMDD, year.frac, MJD, week, day,
               reflon, e0, east, n0, north, u0, up,
               ant, sig_e, sig_n, sig_u, corr_en, corr_eu, corr_nu
    
    We care about: east, north, up (displacement in meters from reference)
    and sig_e, sig_n, sig_u (uncertainties)
    
    Why IGS14 not IGS20? IGS20 is newer but UNR is still reprocessing their
    full archive into it. IGS14 gives us the complete 2010-2024 history we need.
    """
    # UNR uses uppercase station codes in the URL
    code = station_code.upper()
    url = f"{BASE_URL}/{code}.tenv3"

    print(f"  Fetching {station_code} ({station_name})...", end=" ", flush=True)

    try:
        resp = requests.get(url, timeout=120)

        if resp.status_code == 404:
            print("NOT FOUND — skipping")
            return None

        resp.raise_for_status()

    except requests.exceptions.Timeout:
        print("TIMEOUT — skipping")
        return None
    except requests.exceptions.RequestException as e:
        print(f"ERROR: {e} — skipping")
        return None

    # Parse the tenv3 format
    # The file has a single header line then space-separated data
    try:
        df = pd.read_csv(
            io.StringIO(resp.text),
            sep=r"\s+",       # any whitespace as separator
            header=0,         # first line is column names
        )
    except Exception as e:
        print(f"parse error: {e} — skipping")
        return None

    if df.empty:
        print("empty file — skipping")
        return None

    # Rename to our standard schema
    # tenv3 columns: site YYMMMDD yyyy.yyyy MJD week day reflon e0(deg)
    #                east(m) n0(deg) north(m) u0(m) up(m) ant
    #                sig_e(m) sig_n(m) sig_u(m) corr_en corr_eu corr_nu
        # Strip whitespace from column names first
    df.columns = [c.strip() for c in df.columns]

    # Rename to our standard schema — using exact column names from the file
    rename_map = {
        "YYMMMDD":       "date_str",
        "yyyy.yyyy":     "year_frac",
        "__east(m)":     "east_m",
        "_north(m)":     "north_m",
        "____up(m)":     "up_m",
        "sig_e(m)":      "east_sig",
        "sig_n(m)":      "north_sig",
        "sig_u(m)":      "up_sig",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Parse date from YYMMMDD format e.g. "98JUL28" = July 28, 1998
    if "date_str" in df.columns:
        try:
            df["date"] = pd.to_datetime(df["date_str"], format="%y%b%d")
        except Exception:
            df["date"] = pd.to_datetime(df["year_frac"].apply(
                lambda y: pd.Timestamp(int(y), 1, 1) +
                          pd.Timedelta(days=(y % 1) * 365.25)
            ))

    df["station_code"] = station_code
    df["station_name"] = station_name

    # Convert meters to millimeters
    for col in ["east_m", "north_m", "up_m"]:
        if col in df.columns:
            df[col.replace("_m", "_mm")] = df[col] * 1000

    keep_cols = ["date", "north_mm", "east_mm", "up_mm",
                 "north_sig", "east_sig", "up_sig",
                 "station_code", "station_name"]
    df = df[[c for c in keep_cols if c in df.columns]]
    df = df.dropna(subset=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    print(f"{len(df):,} days ({df['date'].min().date()} to {df['date'].max().date()})")
    return df


def fetch_all_stations():
    all_dfs = []

    print("Fetching UNR GPS station data (no login required)...")
    for code, name in STATIONS.items():
        df = fetch_station(code, name)
        if df is not None:
            all_dfs.append(df)
        time.sleep(1.0)

    if not all_dfs:
        raise RuntimeError("No GPS data retrieved — check internet connection")

    combined = pd.concat(all_dfs, ignore_index=True)
    print(f"\nTotal records: {len(combined):,}")
    print(f"Stations retrieved: {combined['station_code'].nunique()}/{len(STATIONS)}")
    print(combined.groupby("station_code")["date"].agg(["min", "max", "count"]).to_string())
    return combined


if __name__ == "__main__":
    print("Testing with single station (BKMS - Parkfield)...")
    test = fetch_station("BKMS", "Parkfield")

    if test is None:
        print("\nTest failed. Try opening this URL in your browser to check:")
        print("https://geodesy.unr.edu/gps_timeseries/tenv3/BKMS.tenv3")
        exit(1)

    print(f"\nTest passed — {len(test)} days of data")
    print(f"Columns: {list(test.columns)}")
    print(test.head(3).to_string())
    print()

    Path("data/raw").mkdir(parents=True, exist_ok=True)
    df = fetch_all_stations()

    out_path = Path("data/raw/gps_raw.parquet")
    df.to_parquet(out_path, index=False)
    print(f"\nSaved to {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")