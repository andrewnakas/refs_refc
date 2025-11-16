#!/usr/bin/env python3
"""
Create pixel-perfect Leaflet image overlay from RRFS GRIB data.
Uses EXACT bounds from the GRIB file - no guessing!
"""

import numpy as np
from PIL import Image
from pathlib import Path
import json
from scipy.interpolate import griddata

try:
    import xarray as xr
    import cfgrib
    HAS_CFGRIB = True
except ImportError:
    HAS_CFGRIB = False

try:
    import pygrib
    HAS_PYGRIB = True
except ImportError:
    HAS_PYGRIB = False


DATA_DIR = Path("rrfs_data")
OUTPUT_DIR = Path("docs")
TILES_DIR = OUTPUT_DIR / "tiles"

# NWS Radar colors (official) - RGBA format
REFC_COLORS = [
    (0, (0, 0, 0, 0)),             # Transparent
    (5, (4, 233, 231, 255)),       # Light blue
    (10, (1, 159, 244, 255)),      # Blue
    (15, (3, 0, 244, 255)),        # Dark blue
    (20, (2, 253, 2, 255)),        # Green
    (25, (1, 197, 1, 255)),        # Dark green
    (30, (0, 142, 0, 255)),        # Forest green
    (35, (253, 248, 2, 255)),      # Yellow
    (40, (229, 188, 0, 255)),      # Gold
    (45, (253, 149, 0, 255)),      # Orange
    (50, (253, 0, 0, 255)),        # Red
    (55, (212, 0, 0, 255)),        # Dark red
    (60, (188, 0, 0, 255)),        # Maroon
    (65, (248, 0, 253, 255)),      # Magenta
    (70, (152, 84, 198, 255)),     # Purple
    (75, (253, 253, 253, 255)),    # White
]


def data_to_rgba(data):
    """Convert REFC values to RGBA using NWS colors."""
    rgba = np.zeros((*data.shape, 4), dtype=np.uint8)

    for i in range(len(REFC_COLORS) - 1):
        val_low, color_low = REFC_COLORS[i]
        val_high, color_high = REFC_COLORS[i + 1]

        mask = (data >= val_low) & (data < val_high)
        for j in range(4):
            rgba[mask, j] = color_low[j]

    # Handle maximum values
    mask = data >= REFC_COLORS[-1][0]
    for j in range(4):
        rgba[mask, j] = REFC_COLORS[-1][1][j]

    return rgba


def load_grib_native_grid(grib_file):
    """Load GRIB file and return data with EXACT geographic coordinates."""

    # Check file size
    file_size = grib_file.stat().st_size
    if file_size < 1024:
        print(f"ERROR: File is {file_size} bytes - likely LFS pointer")
        return None, None, None

    print(f"Loading {grib_file.name} ({file_size / 1024 / 1024:.2f} MB)...")

    # Try cfgrib first
    if HAS_CFGRIB:
        try:
            ds = xr.open_dataset(grib_file, engine='cfgrib')

            # Find REFC variable
            refc_var = None
            for var_name in ['refc', 'REFC', 'unknown', 'r']:
                if var_name in ds:
                    refc_var = var_name
                    break

            if refc_var:
                data = ds[refc_var].values
                lats = ds['latitude'].values
                lons = ds['longitude'].values

                print(f"  Loaded variable: {refc_var}")
                print(f"  Data shape: {data.shape}")
                print(f"  Lat/lon shape: {lats.shape}")

                ds.close()
                return data, lats, lons
        except Exception as e:
            print(f"  cfgrib failed: {e}")

    # Try pygrib fallback
    if HAS_PYGRIB:
        try:
            grbs = pygrib.open(str(grib_file))
            grb = grbs.select(name='Maximum/Composite radar reflectivity')[0]
            lats, lons = grb.latlons()
            data = grb.values
            grbs.close()

            print(f"  Loaded with pygrib")
            print(f"  Data shape: {data.shape}")
            return data, lats, lons
        except Exception as e:
            print(f"  pygrib failed: {e}")

    return None, None, None


def create_perfect_leaflet_image(data, lats, lons, output_path, target_width=3000):
    """
    Create pixel-perfect rectangular image for Leaflet overlay.

    Returns the EXACT geographic bounds from the GRIB data.
    """
    print(f"\nCreating perfect Leaflet image...")

    # Get EXACT bounds from the GRIB data
    lat_min = float(np.nanmin(lats))
    lat_max = float(np.nanmax(lats))
    lon_min = float(np.nanmin(lons))
    lon_max = float(np.nanmax(lons))

    print(f"  EXACT bounds from GRIB:")
    print(f"    Latitude:  {lat_min:.6f} to {lat_max:.6f}")
    print(f"    Longitude: {lon_min:.6f} to {lon_max:.6f}")

    # Calculate native grid aspect ratio from data
    lat_extent = lat_max - lat_min
    lon_extent = lon_max - lon_min
    geo_aspect = lon_extent / lat_extent

    print(f"  Geographic extent aspect: {geo_aspect:.3f}")

    # Create output grid maintaining geographic aspect ratio
    output_height = int(target_width / geo_aspect)

    print(f"  Output image size: {target_width} × {output_height}")

    # Create regular lat/lon grid for output
    lat_range = np.linspace(lat_min, lat_max, output_height)
    lon_range = np.linspace(lon_min, lon_max, target_width)
    grid_lon, grid_lat = np.meshgrid(lon_range, lat_range)

    # Flatten input data for griddata
    points = np.column_stack((lons.flatten(), lats.flatten()))
    values = data.flatten()

    # Remove NaN points
    valid_mask = ~np.isnan(values)
    points = points[valid_mask]
    values = values[valid_mask]

    print(f"  Interpolating {len(values):,} valid points...")

    # Interpolate to regular grid using nearest neighbor
    grid_data = griddata(
        points, values, (grid_lon, grid_lat),
        method='nearest',
        fill_value=np.nan
    )

    # Convert to RGBA
    print(f"  Applying NWS radar colors...")
    rgba = data_to_rgba(grid_data)

    # Flip vertically for correct orientation
    rgba = np.flip(rgba, axis=0)

    # Create and save image
    img = Image.fromarray(rgba, mode='RGBA')
    img.save(output_path, 'PNG', optimize=True)

    print(f"  Saved: {output_path.name}")
    print(f"  Image dimensions: {img.size[0]} × {img.size[1]}")

    # Return EXACT bounds for Leaflet
    return {
        'lat_min': lat_min,
        'lat_max': lat_max,
        'lon_min': lon_min,
        'lon_max': lon_max,
        'width': target_width,
        'height': output_height,
        'aspect_ratio': geo_aspect
    }


def main():
    """Generate perfect Leaflet overlay from RRFS GRIB."""
    print("=" * 70)
    print("RRFS REFC Perfect Leaflet Image Generator")
    print("Using EXACT bounds from GRIB - NO GUESSING!")
    print("=" * 70)
    print()

    # Find GRIB file
    grib_files = sorted([f for f in DATA_DIR.glob('*.grib2') if '.subh.' not in f.name])

    if not grib_files:
        print("ERROR: No GRIB files found")
        return 1

    grib_file = grib_files[0]
    print(f"Processing: {grib_file.name}\n")

    # Load native grid data
    data, lats, lons = load_grib_native_grid(grib_file)

    if data is None:
        print("\nERROR: Failed to load GRIB data")
        return 1

    # Create output directory
    TILES_DIR.mkdir(exist_ok=True, parents=True)

    # Create perfect image
    output_path = TILES_DIR / 'refc_perfect.png'
    bounds = create_perfect_leaflet_image(data, lats, lons, output_path)

    # Save metadata with EXACT bounds
    metadata = {
        'image': 'tiles/refc_perfect.png',
        'bounds': bounds,
        'source': 'RRFS GRIB2 file (official NOAA data)',
        'note': 'Bounds are EXACT values from GRIB lat/lon arrays'
    }

    meta_path = OUTPUT_DIR / 'perfect_tile.json'
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"\nMetadata saved: {meta_path.name}")
    print(f"\n{'=' * 70}")
    print("SUCCESS! Perfect image created with exact GRIB bounds")
    print(f"{'=' * 70}")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
