import requests
import geopandas as gpd
import pandas as pd
from pathlib import Path
import io

# USGS Quaternary Fault and Fold Database
# This is the authoritative national fault database, updated regularly,
# and has a working GeoJSON API. It covers all of California's active faults
# and is what USGS uses for their own hazard maps.
# No login required, stable endpoint.
USGS_FAULT_URL = "https://earthquake.usgs.gov/static/lfs/nshm/qfaults/Qfaults_GIS.zip"


def fetch_fault_geometry():
    """
    Downloads the USGS Quaternary Fault database for California.
    
    This is a zipped shapefile — geopandas can read it directly from
    the zip URL without extracting it manually.
    
    Why USGS instead of SCEC CFM?
    The CFM is a 3D model stored in a proprietary format (gocad tsurf)
    that requires specialized software to parse. The USGS Quaternary
    fault database gives us the same 2D fault traces we need for
    mapping and spatial joins, in a standard format, with no parsing
    complexity. For our purposes (assigning earthquakes to fault segments
    and visualizing on a map) it's equivalent.
    """
    print("Downloading USGS Quaternary Fault and Fold Database...")
    print("(This is a ~10MB zip file, may take 30-60 seconds)")

    response = requests.get(USGS_FAULT_URL, timeout=120)
    response.raise_for_status()

    # Write zip to memory buffer — geopandas can read shapefiles
    # directly from a zip file in memory using a special path syntax
    zip_bytes = io.BytesIO(response.content)

    # geopandas reads zipped shapefiles using the zip:// prefix
    # We need to save temporarily and read back
    zip_path = Path("data/raw/qfaults.zip")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(response.content)

    # Read the shapefile from inside the zip
    zip_resolved = str(zip_path.resolve()).replace("\\", "/")
    faults = gpd.read_file(f"/vsizip/{zip_resolved}/SHP/Qfaults_US_Database.shp")

    print(f"Total fault sections nationwide: {len(faults)}")
    print(f"Columns: {list(faults.columns)}")
    print(f"CRS: {faults.crs}")

    # Reproject to standard WGS84 lat/lng if needed
    if faults.crs and faults.crs.to_epsg() != 4326:
        print(f"Reprojecting from {faults.crs} to EPSG:4326...")
        faults = faults.to_crs("EPSG:4326")

    # Filter to California bounding box
    ca_faults = faults.cx[-125:-113.5, 32:42.5].copy()
    print(f"California fault sections: {len(ca_faults)}")

    # Filter to San Andreas fault system specifically
    # The USGS database uses 'fault_name' column
    name_col = None
    for col in ["fault_name", "NAME", "FaultName", "name", "FAULT_NAME"]:
        if col in ca_faults.columns:
            name_col = col
            break

    if name_col:
        san_andreas = ca_faults[
            ca_faults[name_col].str.contains("San Andreas", case=False, na=False)
        ].copy()
        print(f"San Andreas sections: {len(san_andreas)}")
        print(san_andreas[name_col].tolist())
    else:
        print("Could not find name column — saving all CA faults")
        print(f"Available columns: {list(ca_faults.columns)}")
        san_andreas = ca_faults

    return ca_faults, san_andreas


if __name__ == "__main__":
    Path("data/raw").mkdir(parents=True, exist_ok=True)

    ca_faults, san_andreas = fetch_fault_geometry()

    # Save outputs
    out_ca = Path("data/raw/california_faults.geojson")
    out_sa = Path("data/raw/san_andreas_faults.geojson")

    ca_faults.to_file(out_ca, driver="GeoJSON")
    san_andreas.to_file(out_sa, driver="GeoJSON")

    print(f"\nSaved {out_ca} ({out_ca.stat().st_size / 1e6:.1f} MB)")
    print(f"Saved {out_sa} ({out_sa.stat().st_size / 1e6:.1f} MB)")

    # Clean up the zip file — we have the GeoJSONs now
    import time
time.sleep(2)
try:
    Path("data/raw/qfaults.zip").unlink()
    print("Cleaned up zip file.")
except PermissionError:
    print("Note: could not delete qfaults.zip (still in use) — you can delete it manually.")
print("Done.")