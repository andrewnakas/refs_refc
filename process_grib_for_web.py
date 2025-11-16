#!/usr/bin/env python3
"""
Process RRFS REFC GRIB2 files for web visualization.
Converts GRIB2 data to GeoJSON and PNG tiles for Leaflet maps.
Handles rotated lat-lon grids by reprojecting to regular geographic grid.
"""

import os
import sys
import json
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from PIL import Image
import subprocess
from scipy.interpolate import griddata

# Try importing GRIB libraries
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

# RRFS_NA_3km official grid specification
# Source: UFS SRWeather App predef_grid_params.yaml
RRFS_NA_ROTATION = {
    'south_pole_lat': -35.0,  # Southern pole of rotated grid
    'south_pole_lon': 247.0,  # Southern pole longitude (or -113.0°W)
    'grid_center_lat': 55.0,  # Physical grid center
    'grid_center_lon': -112.5  # Physical grid center
}

# North America focused bounds for output (based on actual RRFS_NA coverage)
NA_BOUNDS = {
    'lat_min': 15.0,
    'lat_max': 75.0,
    'lon_min': -180.0,
    'lon_max': -40.0
}


def setup_output_dirs():
    """Create output directories."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    TILES_DIR.mkdir(exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR.absolute()}")
    print(f"Tiles directory: {TILES_DIR.absolute()}")


def get_refc_bounds_from_wgrib2(grib_file: Path) -> dict:
    """
    Extract grid bounds from GRIB file using wgrib2.
    """
    try:
        # Get grid info using wgrib2
        result = subprocess.run(
            ['wgrib2', str(grib_file), '-grid', '-npts'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return None

        output = result.stdout

        # Parse grid information
        grid_info = {}
        for line in output.split('\n'):
            if 'lat-lon' in line or 'Lambert' in line or 'rotated' in line:
                # Extract grid parameters
                pass

        return grid_info

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def process_with_pygrib(grib_file: Path) -> dict:
    """
    Process GRIB file using pygrib.
    Returns dictionary with data and metadata.
    """
    print(f"Processing {grib_file.name} with pygrib...")

    grbs = pygrib.open(str(grib_file))
    refc = grbs.select(name='Composite reflectivity')[0]

    # Get data and coordinates
    data = refc.values
    lats, lons = refc.latlons()

    # Get grid info with fallback defaults
    try:
        nx = refc.Nx
        ny = refc.Ny
    except:
        ny, nx = data.shape

    # Get actual geographic bounds
    lat_min = float(np.nanmin(lats)) if lats is not None else 20.0
    lat_max = float(np.nanmax(lats)) if lats is not None else 55.0
    lon_min = float(np.nanmin(lons)) if lons is not None else -130.0
    lon_max = float(np.nanmax(lons)) if lons is not None else -60.0

    grid_info = {
        'nx': nx,
        'ny': ny,
        'lat_min': lat_min,
        'lat_max': lat_max,
        'lon_min': lon_min,
        'lon_max': lon_max,
        'projection': refc.projparams if hasattr(refc, 'projparams') else 'unknown',
        'grid_spacing': getattr(refc, 'iDirectionIncrementInDegrees', 0.025)
    }

    print(f"  Grid bounds: lat=[{lat_min:.2f}, {lat_max:.2f}], lon=[{lon_min:.2f}, {lon_max:.2f}]")
    print(f"  Grid type: {grid_info.get('projection', 'unknown')}, Size: {nx}x{ny}")

    grbs.close()

    return {
        'data': data,
        'lats': lats,
        'lons': lons,
        'grid_info': grid_info
    }


def process_with_cfgrib(grib_file: Path) -> dict:
    """
    Process GRIB file using cfgrib/xarray.
    Returns dictionary with data and metadata.
    """
    print(f"Processing {grib_file.name} with cfgrib...")

    ds = xr.open_dataset(
        grib_file,
        engine='cfgrib',
        backend_kwargs={'errors': 'ignore'}
    )

    # Find REFC variable (might be named differently)
    refc_var = None
    for var in ds.data_vars:
        var_attrs = ds[var].attrs
        var_name = str(var).lower()
        var_long_name = str(var_attrs.get('long_name', '')).lower()
        var_standard_name = str(var_attrs.get('standard_name', '')).lower()

        if 'refc' in var_name or 'reflectivity' in var_long_name or 'reflectivity' in var_standard_name:
            refc_var = var
            break

    if refc_var is None:
        # Try to find it by standard name or other attributes
        print(f"  Warning: Could not identify REFC variable, using first variable")
        refc_var = list(ds.data_vars)[0]  # Take first variable as fallback

    data = ds[refc_var].values

    # Get coordinates
    if 'latitude' in ds.coords and 'longitude' in ds.coords:
        lats = ds['latitude'].values
        lons = ds['longitude'].values
    elif 'lat' in ds.coords and 'lon' in ds.coords:
        lats = ds['lat'].values
        lons = ds['lon'].values
    else:
        # Try to get from x, y coordinates
        lats = ds['y'].values if 'y' in ds.coords else None
        lons = ds['x'].values if 'x' in ds.coords else None

    # Handle 1D vs 2D coordinate arrays
    if lats is not None and lons is not None:
        if lats.ndim == 1 and lons.ndim == 1:
            # 1D arrays - create meshgrid
            lons_2d, lats_2d = np.meshgrid(lons, lats)
            lats = lats_2d
            lons = lons_2d

    # Get actual geographic bounds from the data
    # Use nanmin/nanmax to handle any missing values
    lat_min = float(np.nanmin(lats)) if lats is not None else 20.0
    lat_max = float(np.nanmax(lats)) if lats is not None else 55.0
    lon_min = float(np.nanmin(lons)) if lons is not None else -130.0
    lon_max = float(np.nanmax(lons)) if lons is not None else -60.0

    # Get grid metadata
    grid_type = ds.attrs.get('GRIB_gridType', 'unknown')
    var_attrs = ds[refc_var].attrs

    grid_info = {
        'lat_min': lat_min,
        'lat_max': lat_max,
        'lon_min': lon_min,
        'lon_max': lon_max,
        'projection': grid_type,
        'nx': var_attrs.get('GRIB_Nx', data.shape[1] if data.ndim == 2 else 0),
        'ny': var_attrs.get('GRIB_Ny', data.shape[0] if data.ndim == 2 else 0),
        'grid_spacing': var_attrs.get('GRIB_iDirectionIncrementInDegrees', 0.025)
    }

    print(f"  Grid bounds: lat=[{lat_min:.2f}, {lat_max:.2f}], lon=[{lon_min:.2f}, {lon_max:.2f}]")
    print(f"  Grid type: {grid_type}, Size: {grid_info['nx']}x{grid_info['ny']}")

    ds.close()

    return {
        'data': data,
        'lats': lats,
        'lons': lons,
        'grid_info': grid_info
    }


def create_refc_colormap():
    """
    Create NWS-style radar reflectivity colormap.
    Returns tuple of (levels, colors) for REFC visualization.
    """
    # NWS reflectivity color scale (dBZ thresholds and RGB colors)
    levels = [-30, -20, -10, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75]
    colors = [
        (0, 0, 0, 0),          # Transparent for very low values
        (4, 233, 231, 255),    # Light blue
        (1, 159, 244, 255),    # Blue
        (3, 0, 244, 255),      # Dark blue
        (2, 253, 2, 255),      # Green
        (1, 197, 1, 255),      # Dark green
        (0, 142, 0, 255),      # Darker green
        (253, 248, 2, 255),    # Yellow
        (229, 188, 0, 255),    # Gold
        (253, 139, 0, 255),    # Orange
        (212, 0, 0, 255),      # Red
        (188, 0, 0, 255),      # Dark red
        (248, 0, 253, 255),    # Magenta
        (152, 84, 198, 255),   # Purple
        (253, 253, 253, 255),  # White
        (230, 230, 230, 255),  # Light gray
        (200, 200, 200, 255),  # Gray
        (150, 150, 150, 255),  # Dark gray
    ]

    return levels, colors


def data_to_rgba(data: np.ndarray) -> np.ndarray:
    """
    Convert REFC data to RGBA image using NWS color scale.
    """
    levels, colors = create_refc_colormap()

    # Create RGBA array
    rgba = np.zeros((*data.shape, 4), dtype=np.uint8)

    # Apply color scale
    for i in range(len(levels) - 1):
        mask = (data >= levels[i]) & (data < levels[i + 1])
        rgba[mask] = colors[i]

    # Handle values above max level
    mask = data >= levels[-1]
    rgba[mask] = colors[-1]

    return rgba


def reproject_to_regular_grid(data: np.ndarray, lats: np.ndarray, lons: np.ndarray,
                              output_resolution: float = 0.05,
                              focus_region: dict = None) -> tuple:
    """
    Reproject data from rotated/irregular grid to regular geographic lat-lon grid.

    The GRIB lat/lon arrays are already in geographic coordinates (rotation has been applied).
    We interpolate from the curvilinear grid to a regular grid focused on North America.

    Args:
        data: 2D array of data values
        lats: 2D array of latitudes for each data point (already in geographic coords)
        lons: 2D array of longitudes for each data point (already in geographic coords)
        output_resolution: Resolution of output grid in degrees
        focus_region: Dict with lat_min, lat_max, lon_min, lon_max to focus output

    Returns:
        Tuple of (regridded_data, output_lats, output_lons)
    """
    print(f"  Regridding from curvilinear to regular geographic grid...")

    # Flatten the arrays for griddata
    points = np.column_stack((lons.flatten(), lats.flatten()))
    values = data.flatten()

    # Remove NaN or invalid points
    valid_mask = ~(np.isnan(values) | np.isnan(points[:, 0]) | np.isnan(points[:, 1]))
    points = points[valid_mask]
    values = values[valid_mask]

    # Use focus region if provided, otherwise use full data extent
    if focus_region:
        lat_min = focus_region['lat_min']
        lat_max = focus_region['lat_max']
        lon_min = focus_region['lon_min']
        lon_max = focus_region['lon_max']
        print(f"  Using focus region: lat [{lat_min:.1f}, {lat_max:.1f}], lon [{lon_min:.1f}, {lon_max:.1f}]")
    else:
        # Determine extent from corner coordinates (not all data points to avoid -180/180 wraparound)
        lat_min = max(float(lats.min()) - 1, -90)
        lat_max = min(float(lats.max()) + 1, 90)
        # For longitude, use corners to avoid -180/180 issue
        lon_corners = [lons[0,0], lons[0,-1], lons[-1,0], lons[-1,-1]]
        lon_min = max(min(lon_corners) - 1, -180)
        lon_max = min(max(lon_corners) + 1, 180)
        print(f"  Computed extent: lat [{lat_min:.1f}, {lat_max:.1f}], lon [{lon_min:.1f}, {lon_max:.1f}]")

    # Create regular output grid
    lat_range = np.arange(lat_min, lat_max + output_resolution, output_resolution)
    lon_range = np.arange(lon_min, lon_max + output_resolution, output_resolution)

    grid_lon, grid_lat = np.meshgrid(lon_range, lat_range)

    print(f"  Output grid: {len(lat_range)} x {len(lon_range)} = {len(lat_range) * len(lon_range):,} points")
    print(f"  Input points: {len(values):,} valid data points")

    # Interpolate to regular grid using nearest neighbor (preserves discrete radar values)
    grid_data = griddata(points, values, (grid_lon, grid_lat), method='nearest', fill_value=np.nan)

    print(f"  Regridding complete: {grid_data.shape}")

    return grid_data, grid_lat, grid_lon


def create_png_tile(data: np.ndarray, output_path: Path):
    """
    Create PNG tile from REFC data.
    """
    # Convert to RGBA
    rgba = data_to_rgba(data)

    # Flip vertically for proper orientation
    rgba = np.flip(rgba, axis=0)

    # Create and save image
    img = Image.fromarray(rgba, mode='RGBA')
    img.save(output_path, 'PNG', optimize=True)

    print(f"  Created tile: {output_path.name} ({img.size[0]}x{img.size[1]})")


def process_grib_file(grib_file: Path, forecast_hour: int) -> dict:
    """
    Process a single GRIB file and create web assets.
    Reprojects RRFS rotated grid to regular grid focused on North America.
    """
    print(f"\nProcessing {grib_file.name}...")

    # Try to process with available library
    result = None
    if HAS_PYGRIB:
        try:
            result = process_with_pygrib(grib_file)
        except Exception as e:
            print(f"  Error with pygrib: {e}")

    if result is None and HAS_CFGRIB:
        try:
            result = process_with_cfgrib(grib_file)
        except Exception as e:
            print(f"  Error with cfgrib: {e}")

    if result is None:
        print(f"  Skipping {grib_file.name} - no GRIB library available")
        return None

    # Reproject to regular geographic grid focused on North America
    try:
        regridded_data, grid_lats, grid_lons = reproject_to_regular_grid(
            result['data'],
            result['lats'],
            result['lons'],
            output_resolution=0.05,  # 0.05 degree = ~5.5km resolution
            focus_region=NA_BOUNDS  # Focus on North America region
        )

        # Get actual bounds from regridded data
        actual_lat_min = float(np.nanmin(grid_lats))
        actual_lat_max = float(np.nanmax(grid_lats))
        actual_lon_min = float(np.nanmin(grid_lons))
        actual_lon_max = float(np.nanmax(grid_lons))

    except Exception as e:
        print(f"  Error during reprojection: {e}")
        import traceback
        traceback.print_exc()
        return None

    # Create PNG tile from reprojected data
    tile_path = TILES_DIR / f"refc_f{forecast_hour:03d}.png"
    create_png_tile(regridded_data, tile_path)

    # Create metadata with actual reprojected bounds
    metadata = {
        'forecast_hour': forecast_hour,
        'file': grib_file.name,
        'tile': f"tiles/refc_f{forecast_hour:03d}.png",
        'grid': {
            'lat_min': actual_lat_min,
            'lat_max': actual_lat_max,
            'lon_min': actual_lon_min,
            'lon_max': actual_lon_max,
            'projection': 'regular_ll',
            'reprojected': True,
            'source_grid': 'RRFS_NA_3km',
            'original_projection': result['grid_info'].get('projection', 'rotated_ll')
        },
        'stats': {
            'min': float(np.nanmin(regridded_data)),
            'max': float(np.nanmax(regridded_data)),
            'mean': float(np.nanmean(regridded_data))
        }
    }

    return metadata


def process_all_gribs():
    """
    Process all GRIB files in data directory.
    """
    # Load existing metadata
    metadata_file = DATA_DIR / 'metadata.json'
    if metadata_file.exists():
        with open(metadata_file) as f:
            source_meta = json.load(f)
    else:
        source_meta = {}

    # Find all GRIB files (non-subhourly)
    grib_files = sorted([
        f for f in DATA_DIR.glob("*.grib2")
        if '.subh.' not in f.name
    ])

    if not grib_files:
        print("No GRIB files found")
        return None

    print(f"Found {len(grib_files)} GRIB files to process")

    # Process each file
    forecast_metadata = []
    for grib_file in grib_files:
        # Extract forecast hour from filename
        try:
            fhour_str = grib_file.name.split('.f')[1].split('.')[0]
            fhour = int(fhour_str)
        except (IndexError, ValueError):
            print(f"  Could not parse forecast hour from {grib_file.name}")
            continue

        meta = process_grib_file(grib_file, fhour)
        if meta:
            forecast_metadata.append(meta)

    # Determine bounds from first successful forecast or use default extents
    if forecast_metadata:
        bounds = forecast_metadata[0]['grid']
    else:
        print("  Warning: No forecasts processed successfully, using default RRFS_NA bounds")
        # RRFS_NA_3km default bounds (approximate full extent after rotation)
        bounds = {
            'lat_min': -2.0,
            'lat_max': 90.0,
            'lon_min': -180.0,
            'lon_max': 180.0,
            'projection': 'regular_ll',
            'reprojected': True,
            'source_grid': 'RRFS_NA_3km',
            'rotation_params': RRFS_NA_ROTATION
        }

    # Create output metadata
    output_meta = {
        'generated': datetime.now(timezone.utc).isoformat(),
        'source': source_meta,
        'forecasts': forecast_metadata,
        'bounds': bounds
    }

    # Save metadata
    meta_path = OUTPUT_DIR / 'data.json'
    with open(meta_path, 'w') as f:
        json.dump(output_meta, f, indent=2)

    print(f"\nMetadata saved to {meta_path}")

    return output_meta


def main():
    """Main processing routine."""
    print("=" * 60)
    print("RRFS REFC Web Processor")
    print("=" * 60)

    # Check for GRIB libraries
    if not HAS_PYGRIB and not HAS_CFGRIB:
        print("\nERROR: No GRIB library available!")
        print("Please install either:")
        print("  - pygrib: pip install pygrib")
        print("  - cfgrib: pip install cfgrib")
        return 1

    print(f"Using: {'pygrib' if HAS_PYGRIB else 'cfgrib'}")

    setup_output_dirs()

    result = process_all_gribs()

    if result is None:
        print("\nNo data processed")
        return 1

    print("\n" + "=" * 60)
    print(f"Processing complete: {len(result['forecasts'])} forecasts")
    print(f"Output directory: {OUTPUT_DIR.absolute()}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
