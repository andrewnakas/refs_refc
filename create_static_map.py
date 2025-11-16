#!/usr/bin/env python3
"""
Create static map visualization of RRFS REFC data using cartopy with proper rotated pole projection.
Based on NOAA visualization best practices for rotated lat-lon grids.

This generates properly projected static PNG images that can be viewed in a web gallery.
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from pathlib import Path
import json
from datetime import datetime, timezone

try:
    import pygrib
    HAS_PYGRIB = True
except ImportError:
    HAS_PYGRIB = False

try:
    import xarray as xr
    import cfgrib
    HAS_CFGRIB = True
except ImportError:
    HAS_CFGRIB = False


DATA_DIR = Path("rrfs_data")
OUTPUT_DIR = Path("docs")

# RRFS_NA_3km rotated pole parameters from UFS SRWeather App
# The rotated pole is at: -35.0°N, 247.0°E (or -113.0°W)
RRFS_ROTATED_POLE = {
    'pole_latitude': -35.0,  # Grid south pole latitude
    'pole_longitude': 247.0,  # Grid south pole longitude (or -113.0°W)
    'central_rotated_longitude': 0.0  # Central meridian in rotated coords
}

# REFC colormap (radar reflectivity)
REFC_COLORS = [
    (0.0, '#00000000'),      # Transparent for no echo
    (5.0, '#04e9e7'),        # Light blue
    (10.0, '#019ff4'),       # Blue
    (15.0, '#0300f4'),       # Dark blue
    (20.0, '#02fd02'),       # Green
    (25.0, '#01c501'),       # Dark green
    (30.0, '#008e00'),       # Forest green
    (35.0, '#fdf802'),       # Yellow
    (40.0, '#e5bc00'),       # Gold
    (45.0, '#fd9500'),       # Orange
    (50.0, '#fd0000'),       # Red
    (55.0, '#d40000'),       # Dark red
    (60.0, '#bc0000'),       # Maroon
    (65.0, '#f800fd'),       # Magenta
    (70.0, '#9854c6'),       # Purple
    (75.0, '#fdfdfd'),       # White
]


def setup_rotated_pole_projection():
    """
    Create cartopy RotatedPole projection for RRFS_NA_3km grid.

    Based on Stack Overflow solution for rotated pole grids:
    pole_longitude should be adjusted by -180 for cartopy convention.
    """
    rp = ccrs.RotatedPole(
        pole_longitude=RRFS_ROTATED_POLE['pole_longitude'] - 180,
        pole_latitude=RRFS_ROTATED_POLE['pole_latitude'],
        central_rotated_longitude=RRFS_ROTATED_POLE['central_rotated_longitude'],
        globe=ccrs.Globe(semimajor_axis=6371229, semiminor_axis=6371229)
    )
    return rp


def create_refc_colormap():
    """Create custom radar reflectivity colormap."""
    from matplotlib.colors import ListedColormap, BoundaryNorm

    # Extract colors and levels
    levels = [c[0] for c in REFC_COLORS]
    colors = [c[1] for c in REFC_COLORS]

    # Create colormap and norm
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(levels, len(colors))

    return cmap, norm, levels


def create_rrfs_map_with_aspect_ratio(data, lats, lons, output_path, forecast_hour=0, cycle_time=None):
    """
    Create map visualization maintaining proper RRFS grid aspect ratio.

    Args:
        data: 2D array of REFC values
        lats: 2D array of latitudes (already in geographic coords)
        lons: 2D array of longitudes (already in geographic coords)
        output_path: Where to save the figure
        forecast_hour: Forecast hour for title
        cycle_time: Model cycle time
    """
    # Grid dimensions
    ny, nx = data.shape
    aspect_ratio = nx / ny

    print(f"  Grid dimensions: {nx} × {ny}")
    print(f"  Aspect ratio: {aspect_ratio:.3f} (should be ~1.65 for RRFS native grid)")

    # Create figure with proper aspect ratio matching the grid
    # For RRFS native: 4881×2961 = 1.648:1 aspect ratio
    fig_width = 20
    fig_height = fig_width / aspect_ratio
    fig = plt.figure(figsize=(fig_width, fig_height), dpi=100)

    # Use PlateCarree for display (since cfgrib already transformed coords)
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_facecolor('#000000')  # Black background

    # Determine extent from data
    lon_min, lon_max = np.nanmin(lons), np.nanmax(lons)
    lat_min, lat_max = np.nanmin(lats), np.nanmax(lats)

    print(f"  Data extent: lon [{lon_min:.1f}, {lon_max:.1f}], lat [{lat_min:.1f}, {lat_max:.1f}]")

    # Set extent
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())

    # Create radar colormap
    cmap, norm, levels = create_refc_colormap()

    # Plot data using pcolormesh for better performance
    im = ax.pcolormesh(
        lons, lats, data,
        cmap=cmap,
        norm=norm,
        transform=ccrs.PlateCarree(),
        shading='nearest',
        rasterized=True
    )

    # Add geographic features
    ax.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor='white', alpha=0.6)
    ax.add_feature(cfeature.STATES, linewidth=0.4, edgecolor='white', alpha=0.4)
    ax.add_feature(cfeature.BORDERS, linewidth=0.6, edgecolor='white', alpha=0.5)

    # Add gridlines
    gl = ax.gridlines(draw_labels=True, linewidth=0.5, color='white', alpha=0.3, linestyle='--')
    gl.top_labels = False
    gl.right_labels = False

    # Colorbar
    cbar = plt.colorbar(im, ax=ax, orientation='horizontal', pad=0.03, aspect=50, shrink=0.8)
    cbar.set_label('Composite Reflectivity (dBZ)', fontsize=12, color='white')
    cbar.ax.tick_params(labelsize=10, colors='white')

    # Title with cycle and forecast hour info
    if cycle_time:
        title = f'RRFS Composite Reflectivity - Cycle {cycle_time} - F{forecast_hour:03d}'
    else:
        title = f'RRFS Composite Reflectivity (REFC) - F{forecast_hour:03d}'

    ax.set_title(title, fontsize=14, fontweight='bold', color='white', pad=10)

    # Add aspect ratio info as subtle text
    fig.text(0.99, 0.01, f'Grid: {nx}×{ny} | Aspect: {aspect_ratio:.2f}:1',
             ha='right', va='bottom', fontsize=8, color='white', alpha=0.5)

    # Save with black background
    plt.savefig(output_path, dpi=100, bbox_inches='tight', facecolor='black', edgecolor='none')
    plt.close()

    print(f"  Saved: {output_path.name}")


def load_grib_data(grib_file):
    """Load GRIB file and return data, lats, lons."""

    # Check if file is a Git LFS pointer (should be >1KB for real GRIB file)
    file_size = grib_file.stat().st_size
    if file_size < 1024:
        print(f"  ERROR: File is only {file_size} bytes - likely a Git LFS pointer!")
        print(f"  Git LFS files were not downloaded properly.")
        print(f"  Make sure 'git lfs install' and 'git lfs pull' were run successfully.")
        return None, None, None

    print(f"  Loading {grib_file.name} ({file_size / 1024 / 1024:.2f} MB)...")

    if HAS_CFGRIB:
        try:
            # Try opening with cfgrib - may need backend_kwargs for complex GRIB files
            print(f"  Attempting to open with cfgrib...")

            # First try: open without filtering
            try:
                ds = xr.open_dataset(grib_file, engine='cfgrib')
                print(f"  Successfully opened GRIB file")
                print(f"  Available variables: {list(ds.data_vars)}")
            except Exception as e1:
                print(f"  First attempt failed: {e1}")
                print(f"  Trying with backend_kwargs...")

                # Second try: open with filter_by_keys to handle specific messages
                try:
                    ds = xr.open_dataset(
                        grib_file,
                        engine='cfgrib',
                        backend_kwargs={'filter_by_keys': {'parameterName': 'Maximum/Composite radar reflectivity'}}
                    )
                    print(f"  Successfully opened with filter_by_keys")
                except Exception as e2:
                    print(f"  Second attempt failed: {e2}")

                    # Third try: open with errors='ignore'
                    try:
                        ds = xr.open_dataset(
                            grib_file,
                            engine='cfgrib',
                            backend_kwargs={'errors': 'ignore'}
                        )
                        print(f"  Successfully opened with errors='ignore'")
                    except Exception as e3:
                        print(f"  Third attempt failed: {e3}")
                        raise ValueError("All cfgrib opening attempts failed") from e3

            # Get REFC variable (composite reflectivity)
            # Try different possible names
            refc_var = None
            for var_name in ['refc', 'REFC', 'unknown', 'maxrefc', 'composite_reflectivity', 'r']:
                if var_name in ds:
                    refc_var = var_name
                    break

            if refc_var:
                data = ds[refc_var].values
                lats = ds['latitude'].values
                lons = ds['longitude'].values
                print(f"  Successfully loaded '{refc_var}' from GRIB file")
                ds.close()
                return data, lats, lons
            else:
                print(f"  WARNING: REFC variable not found in GRIB file")
                print(f"  Available variables: {list(ds.data_vars)}")
                ds.close()
        except Exception as e:
            print(f"  cfgrib error: {e}")
            import traceback
            traceback.print_exc()

    if HAS_PYGRIB:
        try:
            grbs = pygrib.open(str(grib_file))

            # List all messages
            print(f"  GRIB messages in file:")
            for i, grb in enumerate(grbs):
                print(f"    {i+1}. {grb.name} - {grb.shortName}")
            grbs.rewind()

            # Try to find REFC
            try:
                grb = grbs.select(name='Maximum/Composite radar reflectivity')[0]
            except ValueError:
                # Try alternative names
                try:
                    grb = grbs.select(shortName='refc')[0]
                except ValueError:
                    print(f"  WARNING: Could not find REFC field")
                    grbs.close()
                    return None, None, None

            lats, lons = grb.latlons()
            data = grb.values
            grbs.close()
            print(f"  Successfully loaded REFC from GRIB file with pygrib")
            return data, lats, lons
        except Exception as e:
            print(f"  pygrib error: {e}")
            import traceback
            traceback.print_exc()

    return None, None, None


def process_all_gribs():
    """Process all GRIB files and create static maps."""
    # Load metadata
    metadata_file = DATA_DIR / 'metadata.json'
    if metadata_file.exists():
        with open(metadata_file) as f:
            source_meta = json.load(f)
            cycle_time = f"{source_meta.get('cycle_date', 'Unknown')} {source_meta.get('cycle_hour', '00')}Z"
    else:
        source_meta = {}
        cycle_time = None

    # Find all GRIB files (non-subhourly)
    grib_files = sorted([f for f in DATA_DIR.glob('*.grib2') if '.subh.' not in f.name])

    if not grib_files:
        print("ERROR: No GRIB files found in rrfs_data/")
        return None

    print(f"Found {len(grib_files)} GRIB files to process\n")

    # Create output directory
    maps_dir = OUTPUT_DIR / 'maps'
    maps_dir.mkdir(exist_ok=True, parents=True)

    # Process each file
    forecast_maps = []
    for grib_file in grib_files:
        # Extract forecast hour from filename
        try:
            fhour_str = grib_file.name.split('.f')[1].split('.')[0]
            fhour = int(fhour_str)
        except (IndexError, ValueError):
            print(f"  Could not parse forecast hour from {grib_file.name}")
            continue

        print(f"Processing F{fhour:03d}: {grib_file.name}")

        # Load data
        data, lats, lons = load_grib_data(grib_file)
        if data is None:
            print(f"  Failed to load {grib_file.name}")
            continue

        # Create map
        output_path = maps_dir / f'rrfs_refc_f{fhour:03d}.png'
        create_rrfs_map_with_aspect_ratio(data, lats, lons, output_path, fhour, cycle_time)

        # Get bounds
        lon_min, lon_max = float(np.nanmin(lons)), float(np.nanmax(lons))
        lat_min, lat_max = float(np.nanmin(lats)), float(np.nanmax(lats))
        ny, nx = data.shape

        forecast_maps.append({
            'forecast_hour': fhour,
            'image': f'maps/rrfs_refc_f{fhour:03d}.png',
            'grid': {
                'dimensions': [nx, ny],
                'aspect_ratio': round(nx / ny, 3),
                'lat_min': lat_min,
                'lat_max': lat_max,
                'lon_min': lon_min,
                'lon_max': lon_max,
            }
        })

    if not forecast_maps:
        print("\nERROR: No forecasts were successfully processed!")
        return None

    # Create output metadata
    output_meta = {
        'generated': datetime.now(timezone.utc).isoformat(),
        'source': source_meta,
        'forecasts': forecast_maps,
        'grid_info': {
            'projection': 'rotated_latlon',
            'native_dimensions': [4881, 2961],
            'native_aspect_ratio': 1.648,
            'pole_latitude': RRFS_ROTATED_POLE['pole_latitude'],
            'pole_longitude': RRFS_ROTATED_POLE['pole_longitude'],
        }
    }

    # Save metadata
    meta_path = OUTPUT_DIR / 'maps_data.json'
    with open(meta_path, 'w') as f:
        json.dump(output_meta, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Processing complete!")
    print(f"  Maps created: {len(forecast_maps)}")
    print(f"  Output directory: {maps_dir.absolute()}")
    print(f"  Metadata: {meta_path.name}")
    print(f"{'='*60}")

    return output_meta


def main():
    """Main entry point."""
    print("=" * 60)
    print("RRFS REFC Static Map Generator (Cartopy)")
    print("=" * 60)
    print()

    # Check for GRIB libraries
    if not HAS_PYGRIB and not HAS_CFGRIB:
        print("ERROR: No GRIB library available!")
        print("Please install either:")
        print("  - pygrib: pip install pygrib")
        print("  - cfgrib: pip install cfgrib xarray")
        return 1

    print(f"Using: {'pygrib' if HAS_PYGRIB else 'cfgrib'}")
    print()

    result = process_all_gribs()

    if result is None:
        return 1

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
