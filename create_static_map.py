#!/usr/bin/env python3
"""
Create static map visualization of RRFS REFC data using cartopy with proper rotated pole projection.
Based on NOAA visualization best practices for rotated lat-lon grids.
"""

import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
from pathlib import Path
import json

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


# RRFS_NA_3km rotated pole parameters from UFS SRWeather App
# The rotated pole is at: -35.0°N, 247.0°E (or -113.0°W)
RRFS_ROTATED_POLE = {
    'pole_latitude': -35.0,  # Grid south pole latitude
    'pole_longitude': 247.0,  # Grid south pole longitude (or -113.0°W)
    'central_rotated_longitude': 0.0  # Central meridian in rotated coords
}


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


def create_rrfs_map_with_aspect_ratio(data, lats, lons, output_path):
    """
    Create map visualization maintaining proper RRFS grid aspect ratio.

    Args:
        data: 2D array of REFC values
        lats: 2D array of latitudes (already in geographic coords)
        lons: 2D array of longitudes (already in geographic coords)
        output_path: Where to save the figure
    """
    # Grid dimensions
    ny, nx = data.shape
    aspect_ratio = nx / ny

    print(f"Grid dimensions: {nx} × {ny}")
    print(f"Aspect ratio: {aspect_ratio:.2f}")

    # Create figure with proper aspect ratio
    fig_width = 16
    fig_height = fig_width / aspect_ratio
    fig = plt.figure(figsize=(fig_width, fig_height), dpi=150)

    # Use PlateCarree for display (since cfgrib already transformed coords)
    ax = plt.axes(projection=ccrs.PlateCarree())

    # Determine extent from data
    lon_min, lon_max = np.nanmin(lons), np.nanmax(lons)
    lat_min, lat_max = np.nanmin(lats), np.nanmax(lats)

    print(f"Data extent: lon [{lon_min:.1f}, {lon_max:.1f}], lat [{lat_min:.1f}, {lat_max:.1f}]")

    # Set extent
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())

    # Plot data
    levels = np.arange(0, 76, 5)  # REFC levels 0-75 dBZ
    im = ax.contourf(
        lons, lats, data,
        levels=levels,
        cmap='pyart_NWSRef',  # Radar reflectivity colormap
        transform=ccrs.PlateCarree(),
        extend='max'
    )

    # Add geographic features
    ax.coastlines(resolution='50m', linewidth=0.5, color='white', alpha=0.7)
    ax.gridlines(draw_labels=True, linewidth=0.3, color='white', alpha=0.5)

    # Colorbar
    cbar = plt.colorbar(im, ax=ax, orientation='horizontal', pad=0.05, aspect=40)
    cbar.set_label('Composite Reflectivity (dBZ)', fontsize=12)

    # Title
    ax.set_title('RRFS Composite Reflectivity (REFC) - Native Grid',
                 fontsize=14, fontweight='bold')

    # Save
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    print(f"Saved map to {output_path}")


def load_grib_data(grib_file):
    """Load GRIB file and return data, lats, lons."""
    print(f"Loading {grib_file}...")

    if HAS_CFGRIB:
        try:
            ds = xr.open_dataset(grib_file, engine='cfgrib')
            # Get REFC variable (composite reflectivity)
            if 'refc' in ds:
                data = ds['refc'].values
                lats = ds['latitude'].values
                lons = ds['longitude'].values
                return data, lats, lons
        except Exception as e:
            print(f"cfgrib error: {e}")

    if HAS_PYGRIB:
        try:
            grbs = pygrib.open(str(grib_file))
            grb = grbs.select(name='Maximum/Composite radar reflectivity')[0]
            lats, lons = grb.latlons()
            data = grb.values
            grbs.close()
            return data, lats, lons
        except Exception as e:
            print(f"pygrib error: {e}")

    return None, None, None


def main():
    """Main entry point."""
    # Find first GRIB file
    data_dir = Path('rrfs_data')
    grib_files = sorted([f for f in data_dir.glob('*.grib2') if '.subh.' not in f.name])

    if not grib_files:
        print("No GRIB files found!")
        return 1

    grib_file = grib_files[0]
    print(f"Using: {grib_file.name}")

    # Load data
    data, lats, lons = load_grib_data(grib_file)
    if data is None:
        print("Failed to load GRIB data!")
        return 1

    # Create output directory
    output_dir = Path('docs/static_maps')
    output_dir.mkdir(exist_ok=True, parents=True)

    # Create map
    output_path = output_dir / 'rrfs_refc_native_grid.png'
    create_rrfs_map_with_aspect_ratio(data, lats, lons, output_path)

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
