import pandas as pd
import geopandas as gpd
from pathlib import Path

def validate_usgs(path="data/raw/usgs_2016_2026.parquet"):
    print("=== USGS Earthquake Data ===")
    df = pd.read_parquet(path)

    # Basic shape
    print(f"Rows: {len(df):,}  |  Columns: {df.shape[1]}")

    # Null check — any nulls in critical columns are a problem
    critical = ["time", "latitude", "longitude", "magnitude", "depth_km"]
    nulls = df[critical].isnull().sum()
    if nulls.any():
        print(f"WARNING — nulls found:\n{nulls[nulls > 0]}")
    else:
        print("No nulls in critical columns")

    # Date coverage — should span the full decade
    print(f"Date range: {df['time'].min().date()} to {df['time'].max().date()}")

    # Check for suspicious gaps (any month with zero events is a red flag)
    df["year_month"] = df["time"].dt.to_period("M")
    monthly = df.groupby("year_month").size()
    gaps = monthly[monthly < 10]  # fewer than 10 quakes in a month = suspicious
    if len(gaps) > 0:
        print(f"WARNING — {len(gaps)} months with <10 events: {gaps.index.tolist()}")
    else:
        print("Monthly coverage looks continuous")

    # Coordinate sanity — all should be within California bounds
    out_of_bounds = df[
        (df["latitude"] < 32) | (df["latitude"] > 43) |
        (df["longitude"] < -126) | (df["longitude"] > -113)
    ]
    if len(out_of_bounds) > 0:
        print(f"WARNING — {len(out_of_bounds)} events outside expected bounds")
    else:
        print("All coordinates within California bounding box")

    # Depth check — 33km and 10km exactly are USGS default placeholder depths
    # meaning the true depth is unknown. Worth knowing how many you have.
    placeholder_depths = df[df["depth_km"].isin([10.0, 33.0])]
    pct = len(placeholder_depths) / len(df) * 100
    print(f"Placeholder depths (10km or 33km exactly): {len(placeholder_depths):,} ({pct:.1f}%)")

    print()


def validate_gps(path="data/raw/gps_raw.parquet"):
    print("=== GPS Station Data ===")
    df = pd.read_parquet(path)

    print(f"Rows: {len(df):,}  |  Stations: {df['station_code'].nunique()}")

    for station, group in df.groupby("station_code"):
        date_range = f"{group['date'].min().date()} to {group['date'].max().date()}"

        # Check for large gaps in the time series
        # GPS stations occasionally go offline for maintenance
        group_sorted = group.sort_values("date")
        day_gaps = group_sorted["date"].diff().dt.days
        max_gap = day_gaps.max()
        
        gap_warning = f"  *** max gap: {int(max_gap)} days ***" if max_gap > 30 else ""
        print(f"  {station}: {len(group):,} days | {date_range}{gap_warning}")

    print()


def validate_faults(path="data/raw/san_andreas_faults.geojson"):
    print("=== Fault Geometry ===")
    gdf = gpd.read_file(path)

    print(f"Segments: {len(gdf)}")
    print(f"Coordinate reference system: {gdf.crs}")

    # CRS should be EPSG:4326 (standard lat/lng WGS84)
    # If it's something else, you'll need to reproject before spatial joins
    if str(gdf.crs) != "EPSG:4326":
        print(f"WARNING — unexpected CRS. Reproject with gdf.to_crs('EPSG:4326')")
    else:
        print("CRS is EPSG:4326 — good")

    # Check geometry validity
    invalid = gdf[~gdf.geometry.is_valid]
    if len(invalid) > 0:
        print(f"WARNING — {len(invalid)} invalid geometries")
    else:
        print("All geometries valid")

    print()


if __name__ == "__main__":
    validate_usgs()
    validate_gps()
    validate_faults()
    print("Validation complete.")